"""Views de la API de ejercicios.

Implementa el endpoint central de la plataforma:
POST /api/intentos/ — registra un intento de un estudiante y devuelve
el resultado de la corrección por equivalencia tabular.
"""

import json
import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ejercicios.models import EjercicioPractica, Intento, PracticaComision, Progreso
from ejercicios.progreso import avanzar_progreso
from ejercicios.api.serializers import (
    IntentoComentarioUpdateSerializer,
    IntentoInputSerializer,
    PreviewArgumentoSerializer,
    PreviewDeterminacionSerializer,
    PreviewVerificacionSerializer,
)
from motor import verificar, verificar_argumento, verificar_determinacion
from ejercicios.gemini_hints import generar_pista_gemini
from motor.parser import normalizar_simbolos

logger = logging.getLogger(__name__)


class IntentoCreateView(APIView):
    """Registra un intento de resolución y devuelve feedback inmediato.

    **POST /api/intentos/**

    Recibe la respuesta del estudiante, la compara con la fórmula solución
    del ejercicio usando el motor lógico, guarda el intento, actualiza el
    progreso si corresponde, y devuelve el resultado con las tablas de verdad.

    Permissions:
        El usuario debe estar autenticado (``IsAuthenticated``) e
        **inscripto en la comisión** a la que pertenece la práctica;
        de lo contrario se devuelve 403.

    Request body (JSON):
        .. code-block:: json

            {
                "ejercicio_practica_id": 42,
                "respuesta_raw": "~p | q"
            }

    Response (200 OK — correcto):
        .. code-block:: json

            {
                "correcto": true,
                "error_parse": null,
                "tabla_estudiante": [...],
                "tabla_solucion": [...],
                "intento_id": 17,
                "practica_completa": false
            }

    Response (200 OK — incorrecto o error de parseo):
        .. code-block:: json

            {
                "correcto": false,
                "error_parse": "Carácter no reconocido: '∧'...",
                "tabla_estudiante": null,
                "tabla_solucion": null,
                "intento_id": 18,
                "practica_completa": false
            }

    Response (400 Bad Request):
        Datos de entrada inválidos (campo faltante, id inexistente, etc.).

    Response (500 Internal Server Error):
        La fórmula solución del ejercicio es inválida (bug del sistema).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Procesa un intento de resolución.

        Args:
            request: DRF Request con ``ejercicio_practica_id`` y
                ``respuesta_raw`` en el body JSON.

        Returns:
            DRF Response con el resultado de la corrección.
        """
        # --- Validar input ---
        serializer = IntentoInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ep_id = serializer.validated_data['ejercicio_practica_id']
        diccionario = serializer.validated_data.get('diccionario', {})
        ep = get_object_or_404(
            EjercicioPractica.objects.select_related('practica', 'ejercicio'),
            pk=ep_id,
        )

        # --- Resolver la PracticaComision explícita del request ---
        # No se deduce: un estudiante puede cursar dos comisiones que comparten
        # la misma práctica canónica, y el pc define contra qué fila de Progreso
        # se escribe.
        pc = get_object_or_404(
            PracticaComision.objects.select_related('comision', 'practica'),
            pk=serializer.validated_data['practica_comision_id'],
        )
        if pc.practica_id != ep.practica_id:
            return Response(
                {'detail': 'La práctica del ejercicio no coincide con la comisión indicada.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not pc.comision.estudiantes.filter(pk=request.user.pk).exists():
            return Response(
                {'detail': 'No estás inscripto en esta comisión.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        from cursos.cohortes import cohorte_de

        cohorte = cohorte_de(request.user, pc.comision)
        if cohorte is None:
            return Response(
                {'detail': 'No estás inscripto en esta comisión.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Las fechas de apertura/cierre viven en PracticaComision, que
        # pertenece al aula y se comparte entre camadas: solo aplican a la
        # cohorte en curso. Quien es de una camada anterior y practica para
        # rendir el final tiene que poder seguir enviando intentos (ver
        # ejercicios/views.py, mismo patrón).
        estado = (
            pc.estado_disponibilidad()
            if cohorte.activa
            else 'abierta'
        )
        if estado == 'no_iniciada':
            return Response(
                {'detail': 'La práctica aún no está disponible.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if estado == 'cerrada':
            return Response(
                {'detail': 'La práctica ya cerró.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # --- Llamar al motor lógico (rama por tipo de ejercicio) ---
        try:
            if ep.ejercicio.tipo == 'tabla_verdad':
                # Ejercicio de argumento: formula_solucion es JSON
                try:
                    enunciados_solucion = json.loads(ep.ejercicio.formula_solucion)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(
                        'formula_solucion no es JSON válido en EjercicioPractica pk=%s: %s',
                        ep.pk, e,
                    )
                    return Response(
                        {'detail': 'Error interno en la fórmula del ejercicio.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
                enunciados_estudiante = serializer.validated_data.get('enunciados', [])
                # Normalizar fórmulas del estudiante
                for enunciado in enunciados_estudiante:
                    if 'formula' in enunciado:
                        enunciado['formula'] = normalizar_simbolos(enunciado['formula']).strip()
                juicio_valido = serializer.validated_data.get('juicio_valido', None)
                tabla_estudiante = serializer.validated_data.get('tabla_estudiante') or None
                if tabla_estudiante is None:
                    return Response(
                        {'detail': 'Se requiere tabla_estudiante para ejercicios de tabla de verdad.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                resultado = verificar_argumento(
                    enunciados_estudiante, enunciados_solucion, juicio_valido,
                    tabla_estudiante=tabla_estudiante,
                )
                respuesta_raw_guardada = json.dumps(enunciados_estudiante, ensure_ascii=False)

            elif ep.ejercicio.tipo == 'determinacion_verdad':
                # Ejercicio de determinación de valor de verdad
                respuesta_raw = normalizar_simbolos(serializer.validated_data.get('respuesta_raw', '')).strip()
                valores_verdad_est = serializer.validated_data.get('valores_verdad') or {}
                valor_verdad_est = serializer.validated_data.get('valor_verdad_estudiante', None)
                valores_verdad_sol = ep.ejercicio.valores_verdad_solucion or {}

                if not respuesta_raw:
                    return Response(
                        {'detail': 'Se requiere una fórmula para ejercicios de determinación de verdad.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not valores_verdad_est:
                    return Response(
                        {'detail': 'Debés asignar un valor de verdad (V o F) a cada variable del diccionario.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if valor_verdad_est is None:
                    return Response(
                        {'detail': 'Debés indicar el valor de verdad de tu fórmula (V o F).'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Verificar que todas las variables de la fórmula tengan valor asignado
                from motor.parser import parsear as _parsear_det
                try:
                    _expr_det = _parsear_det(respuesta_raw)
                    vars_faltantes = {s.name for s in _expr_det.free_symbols} - set(valores_verdad_est.keys())
                    if vars_faltantes:
                        return Response(
                            {'detail': f'Faltan valores de verdad para las variables: {sorted(vars_faltantes)}.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                except ValueError:
                    pass  # error_parse lo capturará verificar_determinacion

                resultado = verificar_determinacion(
                    formula_estudiante=respuesta_raw,
                    valores_dict_estudiante=valores_verdad_est,
                    valor_asignado_estudiante=valor_verdad_est,
                    formula_solucion=ep.ejercicio.formula_solucion,
                    valores_dict_solucion=valores_verdad_sol,
                )
                respuesta_raw_guardada = respuesta_raw

            else:
                # Ejercicio de formalización
                respuesta_raw = normalizar_simbolos(serializer.validated_data.get('respuesta_raw', '')).strip()
                resultado = verificar(respuesta_raw, ep.ejercicio.formula_solucion)
                respuesta_raw_guardada = respuesta_raw

                # Validar diccionario: debe estar completo y coincidir con las
                # variables de la fórmula. Se aplica tanto desde la UI como
                # desde llamadas directas a la API.
                if not resultado['error_parse']:
                    from motor.parser import parsear as _parsear
                    try:
                        _expr = _parsear(respuesta_raw)
                        vars_formula = {s.name for s in _expr.free_symbols}

                        if not diccionario and vars_formula:
                            # Diccionario vacío pero la fórmula tiene variables.
                            resultado = {
                                **resultado,
                                'correcto': False,
                                'error_diccionario': (
                                    'Completá el diccionario de enunciados simples '
                                    'antes de enviar la fórmula.'
                                ),
                            }
                        elif diccionario:
                            vars_diccionario = set(diccionario.keys())
                            partes = []
                            sobrantes = vars_formula - vars_diccionario
                            if sobrantes:
                                partes.append(f'usás {sorted(sobrantes)} en la fórmula pero no las definiste en el diccionario')
                            faltantes = vars_diccionario - vars_formula
                            if faltantes:
                                partes.append(f'definiste {sorted(faltantes)} en el diccionario pero no aparecen en la fórmula')
                            if partes:
                                resultado = {
                                    **resultado,
                                    'correcto': False,
                                    'error_diccionario': 'El diccionario no coincide con la fórmula: ' + '; '.join(partes) + '.',
                                }
                    except ValueError:
                        pass  # Ya fue capturado por verificar() arriba
        except RuntimeError as e:
            # Bug en la fórmula solución del docente — error del sistema
            logger.error(
                'Fórmula solución inválida en EjercicioPractica pk=%s: %s',
                ep.pk, e,
            )
            return Response(
                {'detail': 'Error interno en la fórmula del ejercicio.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # --- Guardar intento y actualizar progreso atomicamente ---
        # Para tabla_verdad, persistir también la tabla completada por el estudiante.
        # Para determinacion_verdad, persistir valores_verdad y valor_verdad_estudiante.
        tabla_json_guardada = tabla_estudiante if ep.ejercicio.tipo == 'tabla_verdad' else None
        juicio_estudiante_guardado = (
            juicio_valido if ep.ejercicio.tipo == 'tabla_verdad' else None
        )
        valores_verdad_guardados = (
            serializer.validated_data.get('valores_verdad')
            if ep.ejercicio.tipo == 'determinacion_verdad' else None
        )
        valor_verdad_guardado = (
            serializer.validated_data.get('valor_verdad_estudiante')
            if ep.ejercicio.tipo == 'determinacion_verdad' else None
        )

        with transaction.atomic():
            intento = Intento.objects.create(
                estudiante=request.user,
                ejercicio_practica=ep,
                practica_comision=pc,
                cohorte=cohorte,
                respuesta_raw=respuesta_raw_guardada,
                es_correcto=resultado['correcto'],
                diccionario=diccionario,
                tabla_json=tabla_json_guardada,
                juicio_estudiante=juicio_estudiante_guardado,
                valores_verdad=valores_verdad_guardados,
                valor_verdad_estudiante=valor_verdad_guardado,
            )
            practica_completa = False
            ejercicios_pendientes = None
            if resultado['correcto']:
                practica_completa, ejercicios_pendientes = avanzar_progreso(
                    request.user, ep, pc, cohorte,
                )
                from django.core.cache import cache as _cache
                _cache.delete(f'analiticas_{pc.comision_id}_{cohorte.pk}')

        # Clasificar el error semánticamente (solo formalización incorrecta sin error_parse)
        if (
            not resultado['correcto']
            and ep.ejercicio.tipo == 'formalizacion'
            and not resultado.get('error_parse')
        ):
            try:
                from motor.clasificador import clasificar_error as _clasificar
                categoria = _clasificar(respuesta_raw_guardada, ep.ejercicio.formula_solucion)
                intento.error_categoria = categoria
                intento.save(update_fields=['error_categoria'])
            except Exception as _exc:
                logger.warning(
                    'No se pudo clasificar el error del intento %s: %s', intento.pk, _exc
                )

        from accounts.models import ConfigSitio as _ConfigSitio
        _config = _ConfigSitio.get()

        # Revisar el diccionario estudiantil con Groq (solo intentos correctos con diccionario)
        if resultado['correcto'] and diccionario and _config.revision_diccionario_activa:
            try:
                from ejercicios.gemini_hints import revisar_diccionario_groq as _revisar_dic
                veredicto = _revisar_dic(ep.ejercicio.enunciado, diccionario)
                if veredicto:
                    intento.revision_diccionario = veredicto
                    intento.save(update_fields=['revision_diccionario'])
            except Exception as _exc:
                logger.warning('No se pudo revisar el diccionario del intento %s: %s', intento.pk, _exc)

        pista = None
        if not resultado.get('correcto') and _config.pistas_ia_activas:
            intentos_incorrectos = Intento.objects.filter(
                estudiante=request.user,
                ejercicio_practica=ep,
                es_correcto=False,
            ).count()
            if intentos_incorrectos >= 5:
                pista = generar_pista_gemini(
                    tipo_ejercicio=ep.ejercicio.tipo,
                    enunciado=ep.ejercicio.enunciado,
                    respuesta_estudiante=respuesta_raw_guardada,
                    solucion_esperada=ep.ejercicio.formula_solucion,
                    error_parse=resultado.get('error_parse'),
                    diccionario=diccionario or None,
                    enunciados_estudiante=enunciados_estudiante if ep.ejercicio.tipo == 'tabla_verdad' else None,
                    tabla_estudiante=tabla_estudiante if ep.ejercicio.tipo == 'tabla_verdad' else None,
                    juicio_valido=juicio_valido if ep.ejercicio.tipo == 'tabla_verdad' else None,
                    resultado_motor=resultado,
                )

        return Response({
            **resultado,
            'pista': pista,
            'intento_id': intento.pk,
            'practica_completa': practica_completa,
            'ejercicios_pendientes': ejercicios_pendientes,
        })



class PreviewVerificacionView(APIView):
    """Permite probar corrección contra una fórmula solución en el formulario docente."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Ejecuta una verificación sandbox sin persistir intentos."""
        serializer = PreviewVerificacionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        formula_solucion = normalizar_simbolos(serializer.validated_data['formula_solucion']).strip()
        respuesta_prueba = normalizar_simbolos(serializer.validated_data['respuesta_prueba']).strip()

        try:
            resultado = verificar(respuesta_prueba, formula_solucion)
        except RuntimeError as error:
            return Response(
                {'formula_solucion': [f'La fórmula solución no es una fórmula bien formada (fbf). ({error})']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(resultado, status=status.HTTP_200_OK)


class PreviewArgumentoView(APIView):
    """Permite probar un argumento lógico en el formulario docente (sandbox)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Ejecuta verificación de argumento sin persistir intentos."""
        serializer = PreviewArgumentoSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        enunciados_solucion = serializer.validated_data.get('enunciados_solucion') or None
        enunciados_prueba = serializer.validated_data['enunciados_prueba']
        juicio_valido = serializer.validated_data.get('juicio_valido', None)

        # Si no se proporcionó solución, usar los enunciados_prueba como referencia
        # (útil cuando el estudiante genera la tabla vacía en el Paso 3).
        if not enunciados_solucion:
            enunciados_solucion = enunciados_prueba

        # Normalizar fórmulas
        for enunciado in enunciados_solucion:
            if 'formula' in enunciado:
                enunciado['formula'] = normalizar_simbolos(enunciado['formula']).strip()
        for enunciado in enunciados_prueba:
            if 'formula' in enunciado:
                enunciado['formula'] = normalizar_simbolos(enunciado['formula']).strip()

        try:
            resultado = verificar_argumento(enunciados_prueba, enunciados_solucion, juicio_valido)
        except RuntimeError as error:
            return Response(
                {'enunciados_solucion': [f'Una fórmula de la solución no es válida. ({error})']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(resultado, status=status.HTTP_200_OK)


class IntentoComentarioUpdateView(APIView):
    """Actualiza el comentario docente de un intento sin alterar su resultado."""

    permission_classes = [IsAuthenticated]

    def post(self, request, intento_id):
        """Guarda o edita el comentario asociado a un intento específico."""
        serializer = IntentoComentarioUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        intento = get_object_or_404(
            Intento.objects.select_related('practica_comision__comision', 'estudiante'),
            pk=intento_id,
        )

        if not (request.user.is_staff or request.user.es_docente):
            return Response({'detail': 'No tenés permisos para editar comentarios.'}, status=status.HTTP_403_FORBIDDEN)

        if not request.user.is_staff:
            es_docente_de_comision = intento.practica_comision.comision.docentes.filter(
                pk=request.user.pk
            ).exists()
            if not es_docente_de_comision:
                return Response({'detail': 'No tenés permisos sobre este intento.'}, status=status.HTTP_403_FORBIDDEN)

        intento.comentario_docente = serializer.validated_data['comentario_docente']
        intento.save(update_fields=['comentario_docente'])

        return Response({
            'intento_id': intento.pk,
            'comentario_docente': intento.comentario_docente,
        }, status=status.HTTP_200_OK)


class PreviewDeterminacionView(APIView):
    """Evalúa puntualmente una fórmula con valores de verdad dados.

    Permite al docente ver en tiempo real el valor de verdad de su fórmula
    solución según el diccionario que está construyendo, sin persistir nada.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Evalúa la fórmula con los valores de verdad provistos."""
        serializer = PreviewDeterminacionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        formula = normalizar_simbolos(serializer.validated_data['formula']).strip()
        valores_verdad = serializer.validated_data['valores_verdad']

        from motor.parser import parsear as _parsear, validar_parentesis_en_operaciones_mixtas
        from motor.verificador import _evaluar_con_valores
        from sympy import Symbol

        try:
            validar_parentesis_en_operaciones_mixtas(formula)
            expr = _parsear(formula)
        except ValueError as e:
            return Response(
                {'error_parse': f'La fórmula no es una fórmula bien formada (fbf). ({e})'},
                status=status.HTTP_200_OK,
            )

        vars_formula = {s.name for s in expr.free_symbols}
        vars_faltantes = vars_formula - set(valores_verdad.keys())
        if vars_faltantes:
            return Response(
                {'error_parse': f'Las variables {sorted(vars_faltantes)} no tienen valor asignado en el diccionario.'},
                status=status.HTTP_200_OK,
            )

        valor = _evaluar_con_valores(expr, valores_verdad)
        return Response({'valor': valor, 'error_parse': None}, status=status.HTTP_200_OK)
