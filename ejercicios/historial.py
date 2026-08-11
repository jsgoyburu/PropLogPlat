"""Armado del historial de intentos de un estudiante.

Vive en ``ejercicios`` porque los datos son ``Intento``; ``docentes`` lo
importa para su panel. Mismo criterio que ``cursos/cohortes.py``: un modulo
sin dependencias de vistas, importable desde las dos apps sin ciclo.
"""

import json

from ejercicios.models import Intento, PracticaComision


def _enriquecer_intento(intento):
    """Agrega atributos parseados al intento para la presentacion en template."""
    tipo = intento.ejercicio_practica.ejercicio.tipo

    if tipo == 'tabla_verdad':
        try:
            intento.enunciados_parsed = json.loads(intento.respuesta_raw)
        except (ValueError, TypeError):
            intento.enunciados_parsed = None
    else:
        intento.enunciados_parsed = None

    # Para determinacion_verdad: combinar diccionario + valores_verdad en una
    # lista legible.
    if tipo == 'determinacion_verdad':
        dic = intento.diccionario or {}
        vv = intento.valores_verdad or {}
        intento.diccionario_con_valores = [
            {
                'letra': letra,
                'frase': frase,
                'valor': vv.get(letra),  # True / False / None
            }
            for letra, frase in dic.items()
        ]
    else:
        intento.diccionario_con_valores = None

    # tabla_json ya es un JSONField nativo (list o None): no necesita parseo.
    return intento


def build_historial_context(estudiante, comisiones, comision_id=None, pc_id=None):
    """Contexto del historial de ``estudiante``, agrupado por ejercicio.

    Args:
        estudiante: usuario del que se muestran los intentos.
        comisiones: queryset/lista de comisiones disponibles para filtrar.
        comision_id: id de comision seleccionada (opcional).
        pc_id: id de PracticaComision seleccionada (opcional).

    Returns:
        dict: filtros activos, opciones y lista de secciones por cohorte. Cada
        seccion es ``{'cohorte': Cohorte, 'grupos': [...]}`` y las camadas
        salen con la mas reciente primero.
    """
    comisiones = list(comisiones)
    comisiones_por_id = {comision.id: comision for comision in comisiones}
    comision_seleccionada = comisiones_por_id.get(comision_id)

    pcs_queryset = (
        PracticaComision.objects
        .filter(comision__in=comisiones)
        .select_related('practica', 'comision')
        .order_by('comision__nombre', 'orden')
    )
    if comision_seleccionada is not None:
        pcs_queryset = pcs_queryset.filter(comision=comision_seleccionada)
    pcs = list(pcs_queryset)
    pcs_por_id = {pc.id: pc for pc in pcs}
    pc_seleccionado = pcs_por_id.get(pc_id)

    intentos_queryset = (
        Intento.objects.filter(
            estudiante=estudiante,
            practica_comision__comision__in=comisiones,
        )
        .select_related(
            'cohorte',
            'ejercicio_practica__practica',
            'ejercicio_practica__ejercicio',
            'practica_comision__comision',
        )
        .order_by(
            # Cohorte.Meta.ordering no se aplica al atravesar la FK desde
            # Intento, por eso el orden de camada va explicito.
            '-cohorte__anio',
            '-cohorte__cuatrimestre',
            'practica_comision__comision__nombre',
            'practica_comision__orden',
            'ejercicio_practica__orden',
            '-timestamp',
        )
    )
    if comision_seleccionada is not None:
        intentos_queryset = intentos_queryset.filter(
            practica_comision__comision=comision_seleccionada,
        )
    if pc_seleccionado is not None:
        intentos_queryset = intentos_queryset.filter(practica_comision=pc_seleccionado)

    secciones = []
    secciones_por_cohorte = {}
    grupos_por_clave = {}
    for intento in intentos_queryset:
        _enriquecer_intento(intento)

        cohorte_id = intento.cohorte_id
        if cohorte_id not in secciones_por_cohorte:
            seccion = {'cohorte': intento.cohorte, 'grupos': []}
            secciones_por_cohorte[cohorte_id] = seccion
            secciones.append(seccion)

        # La clave lleva la cohorte: sin eso, las dos camadas de un recursante
        # colapsan en un grupo y ultimo_intento sale de la que ordene primero.
        clave = (cohorte_id, intento.ejercicio_practica_id)
        if clave not in grupos_por_clave:
            grupo = {
                'ejercicio_practica': intento.ejercicio_practica,
                'comision': intento.practica_comision.comision if intento.practica_comision else None,
                'ultimo_intento': intento,
                'intentos_anteriores': [],
                'total_intentos': 1,
            }
            grupos_por_clave[clave] = grupo
            secciones_por_cohorte[cohorte_id]['grupos'].append(grupo)
        else:
            grupos_por_clave[clave]['intentos_anteriores'].append(intento)
            grupos_por_clave[clave]['total_intentos'] += 1

    return {
        'filtro_comision_id': comision_seleccionada.id if comision_seleccionada else '',
        'filtro_pc_id': pc_seleccionado.id if pc_seleccionado else '',
        'comisiones_disponibles': comisiones,
        'practicas_disponibles': pcs,
        'historial_por_cohorte': secciones,
    }
