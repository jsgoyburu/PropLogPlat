"""Vistas HTML de la app ejercicios.

Tres vistas principales para estudiantes:
    - :func:`home`: lista de comisiones y prácticas del estudiante.
    - :func:`practica_detail`: ejercicios de una práctica con estado de desbloqueo.
    - :func:`ejercicio_detail`: ejercicio individual con teclado on-screen (Alpine.js).

Los docentes y admins son redirigidos al panel docente desde :func:`home`.
El acceso a cada ejercicio depende del modo de desbloqueo de la práctica en esa
comisión (``PracticaComision.desbloqueo_secuencial``): secuencial, donde cada
ejercicio se habilita al resolver el anterior, o libre, donde están todos
disponibles. Ver :mod:`ejercicios.progreso` y :class:`ejercicios.models.Progreso`.
"""

import json

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from cursos.models import Comision
from .historial import build_historial_context
from .models import EjercicioPractica, Intento, Practica, PracticaComision, Progreso
from .progreso import esta_resuelto


@login_required
def home(request):
    """Vista principal del estudiante: comisiones y prácticas con estado.

    Los docentes y admins son redirigidos al panel docente.
    Para estudiantes, muestra cada comisión en la que están inscriptos con
    el estado de cada PracticaComision (``None`` = no iniciada, ``'en_curso'``,
    ``'completa'``).
    """
    usuario = request.user
    if usuario.is_staff or usuario.es_docente:
        return redirect('docentes:comisiones_list')

    # .distinct(): estudiantes=usuario hace join contra Inscripcion (M2M por
    # tabla intermedia); un recursante tiene dos Inscripcion en la misma
    # Comision (una por cohorte) y sin distinct() el join devuelve la
    # comisión duplicada.
    comisiones = list(
        Comision.objects.filter(estudiantes=usuario)
        .distinct()
        .prefetch_related(
            Prefetch(
                'practicas_comisiones',
                queryset=PracticaComision.objects.select_related('practica').order_by('orden'),
            )
        )
        .order_by('nombre')
    )

    # El progreso es por (estudiante, practica_comision, cohorte): un recursante
    # tiene una fila por camada para el mismo practica_comision. Resolvemos la
    # cohorte de cada comisión (la de la inscripción más reciente del
    # estudiante en ella, vía cohorte_de) y filtramos cada Progreso por la
    # cohorte de SU comisión, así el dict queda con el progreso de la camada
    # actual del estudiante en cada una, nunca con una fila arbitraria entre
    # las que puede haber para un mismo pc.
    from django.db.models import Q

    from cursos.cohortes import cohorte_de
    filtro_cohortes = Q()
    for comision in comisiones:
        cohorte = cohorte_de(usuario, comision)
        if cohorte is not None:
            filtro_cohortes |= Q(practica_comision__comision_id=comision.id, cohorte_id=cohorte.id)

    progresos_por_pc = {}
    if filtro_cohortes:
        progresos_por_pc = {
            p.practica_comision_id: p
            for p in Progreso.objects.filter(filtro_cohortes, estudiante=usuario)
        }

    comisiones_data = []
    for comision in comisiones:
        practicas_data = []
        for pc in comision.practicas_comisiones.all():
            progreso = progresos_por_pc.get(pc.id)
            if progreso is None:
                estado = None
            else:
                estado = 'completa' if progreso.ejercicio_practica_actual is None else 'en_curso'
            practicas_data.append({'pc': pc, 'practica': pc.practica, 'estado': estado})
        comisiones_data.append({'comision': comision, 'practicas': practicas_data})

    intentos_con_comentario = (
        Intento.objects.filter(
            estudiante=usuario,
            aprobado_docente__isnull=False,
            comentario_docente__isnull=False,
        )
        .exclude(comentario_docente='')
        .select_related(
            'ejercicio_practica__ejercicio',
            'ejercicio_practica__practica',
            'practica_comision__practica',
            'practica_comision__comision',
        )
        .order_by('-timestamp')
    )

    return render(request, 'ejercicios/home.html', {
        'comisiones_data': comisiones_data,
        'intentos_con_comentario': intentos_con_comentario,
    })


@login_required
def practica_detail(request, pc_id):
    """Lista de ejercicios de una práctica con indicadores de estado.

    Para estudiantes, cada EjercicioPractica tiene uno de cinco estados:
        - ``'aprobado'``: aprobado por el docente (verde, ✓).
        - ``'pendiente'``: correcto automáticamente, esperando revisión
          docente (amarillo, 🕐).
        - ``'rechazado'``: último intento incorrecto o rechazado por el
          docente (rojo, 🚫). El estudiante puede volver a intentarlo.
        - ``'actual'``: desbloqueado pero sin intentos aún (azul, →).
        - ``'bloqueado'``: aún no desbloqueado (gris, 🔒). Sólo aparece si la
          práctica está en modo secuencial: con ``desbloqueo_secuencial=False``
          todos los ejercicios están abiertos desde el inicio.

    El estado se determina a partir del **último intento** del estudiante
    para cada EP, no del historial completo.

    El estado se calcula sobre los intentos de **esta** comisión: lo resuelto en
    otra comisión que comparta la misma práctica canónica no se refleja acá.

    Docentes y admins ven todos los ejercicios como ``'aprobado'`` (acceso
    total para previsualización).

    Acceso denegado (redirect a home) si el estudiante no está inscripto
    en la comisión de la práctica.
    """
    usuario = request.user
    pc = get_object_or_404(
        PracticaComision.objects.select_related('practica', 'comision'),
        pk=pc_id,
    )
    practica = pc.practica

    if not (usuario.is_staff or usuario.es_docente):
        if not pc.comision.estudiantes.filter(pk=usuario.pk).exists():
            return redirect('ejercicios:home')

        # Control de período de disponibilidad (solo para estudiantes).
        # Las fechas viven en PracticaComision, que pertenece a la Comision y
        # se comparte entre camadas, así que solo aplican a la cohorte en
        # curso. Quien es de una camada anterior sigue practicando para rendir
        # el final sin quedar afuera por el calendario de la cursada nueva.
        from cursos.cohortes import cohorte_de
        cohorte_est = cohorte_de(usuario, pc.comision)
        estado_disp = (
            pc.estado_disponibilidad()
            if cohorte_est is not None and cohorte_est.activa
            else 'abierta'
        )
        if estado_disp == 'no_iniciada':
            from django.utils import timezone
            return render(request, 'ejercicios/practica_no_disponible.html', {
                'pc': pc,
                'practica': practica,
                'motivo': 'no_iniciada',
                'fecha_apertura': timezone.localtime(pc.fecha_apertura),
            })
        if estado_disp == 'cerrada':
            from django.utils import timezone
            return render(request, 'ejercicios/practica_no_disponible.html', {
                'pc': pc,
                'practica': practica,
                'motivo': 'cerrada',
                'fecha_cierre': timezone.localtime(pc.fecha_cierre),
            })

    eps = list(
        practica.ejercicio_practicas.select_related('ejercicio').order_by('orden')
    )

    if usuario.is_staff or usuario.es_docente:
        eps_data = [{'ep': ep, 'estado': 'aprobado'} for ep in eps]
    else:
        # `cohorte_est` ya viene resuelto del control de disponibilidad.
        ep_ids = [ep.pk for ep in eps]

        # Último intento por EP: necesitamos es_correcto y aprobado_docente.
        # Acotado a la cohorte del estudiante en esta comisión: sin esto, un
        # recursante mezclaría el historial de la camada vieja con la actual.
        from django.db.models import OuterRef, Subquery
        ultimo_intento_qs = (
            Intento.objects
            .filter(estudiante=usuario, ejercicio_practica=OuterRef('pk'),
                    practica_comision=pc, cohorte=cohorte_est)
            .order_by('-timestamp')
            .values('es_correcto', 'aprobado_docente')[:1]
        )
        eps_con_ultimo = (
            EjercicioPractica.objects
            .filter(pk__in=ep_ids)
            .annotate(
                ultimo_es_correcto=Subquery(ultimo_intento_qs.values('es_correcto')),
                ultimo_aprobado_docente=Subquery(ultimo_intento_qs.values('aprobado_docente')),
            )
        )
        ultimo_por_ep = {e.pk: e for e in eps_con_ultimo}

        # EP actual según Progreso
        progreso_existe = False
        ep_actual_id = eps[0].pk if eps else None  # default: sin progreso
        try:
            progreso = Progreso.objects.get(
                estudiante=usuario, practica_comision=pc, cohorte=cohorte_est,
            )
            progreso_existe = True
            ep_actual_id = progreso.ejercicio_practica_actual_id  # None = completa
        except Progreso.DoesNotExist:
            pass

        # Orden del EP actual y flag de "práctica marcada completa"
        ep_actual_orden = None
        practica_marcada_completa = progreso_existe and ep_actual_id is None
        if ep_actual_id is not None:
            ep_actual = next((e for e in eps if e.pk == ep_actual_id), None)
            if ep_actual is not None:
                ep_actual_orden = ep_actual.orden

        eps_data = []
        for ep in eps:
            ann = ultimo_por_ep.get(ep.pk)
            tiene_intento = ann and ann.ultimo_es_correcto is not None
            desbloqueado = (
                not pc.desbloqueo_secuencial
                or practica_marcada_completa
                or (ep_actual_orden is not None and ep.orden <= ep_actual_orden)
            )

            if tiene_intento:
                if ann.ultimo_aprobado_docente is True:
                    estado = 'aprobado'
                elif ann.ultimo_es_correcto and ann.ultimo_aprobado_docente is None:
                    estado = 'pendiente'
                else:
                    estado = 'rechazado'
            elif desbloqueado:
                estado = 'actual'
            else:
                estado = 'bloqueado'

            eps_data.append({'ep': ep, 'estado': estado})

    return render(request, 'ejercicios/practica.html', {
        'pc': pc,
        'practica': practica,
        'eps_data': eps_data,
    })


@login_required
def ejercicio_detail(request, pc_id, ep_id):
    """Vista de un ejercicio individual con teclado on-screen y feedback tabular.

    Determina si el estudiante puede enviar respuestas (``puede_enviar``) según
    el modo de desbloqueo de la práctica en esa comisión
    (``PracticaComision.desbloqueo_secuencial``).

    En modo **secuencial**:

        - ``puede_enviar = True``: el ep es el actual en el Progreso del estudiante,
          o no existe Progreso aún y es el primer ep de la práctica.
        - ``puede_enviar = False``: el ep ya fue resuelto (ver sin enviar),
          o la práctica está completa.
        - Redirect a la práctica: si el ep está bloqueado.

    En modo **libre** no hay gating por orden: ``puede_enviar`` depende sólo de
    si el ejercicio ya está resuelto, y nunca se redirige.

    "Resuelto" usa la correctitud efectiva de :mod:`ejercicios.correctitud`: el
    juicio docente tiene precedencia sobre el resultado del motor.

    Docentes y admins siempre ven los ejercicios en modo lectura (``puede_enviar = False``).
    """
    usuario = request.user
    pc = get_object_or_404(
        PracticaComision.objects.select_related('practica', 'comision'),
        pk=pc_id,
    )
    practica = pc.practica
    ep = get_object_or_404(
        EjercicioPractica.objects.select_related('ejercicio', 'practica'),
        pk=ep_id,
        practica=practica,
    )

    if usuario.is_staff or usuario.es_docente:
        # Modo lectura: docentes/admins ven el ejercicio sin poder enviar
        puede_enviar = False
    else:
        if not pc.comision.estudiantes.filter(pk=usuario.pk).exists():
            return redirect('ejercicios:home')

        # Control de período de disponibilidad. Ver practica_detail: las fechas
        # son del aula y se comparten entre camadas, así que solo frenan a la
        # cohorte en curso.
        from cursos.cohortes import cohorte_de
        cohorte_est = cohorte_de(usuario, pc.comision)
        estado_disp = (
            pc.estado_disponibilidad()
            if cohorte_est is not None and cohorte_est.activa
            else 'abierta'
        )
        if estado_disp == 'no_iniciada':
            from django.utils import timezone
            return render(request, 'ejercicios/practica_no_disponible.html', {
                'pc': pc,
                'practica': practica,
                'motivo': 'no_iniciada',
                'fecha_apertura': timezone.localtime(pc.fecha_apertura),
            })
        if estado_disp == 'cerrada':
            from django.utils import timezone
            return render(request, 'ejercicios/practica_no_disponible.html', {
                'pc': pc,
                'practica': practica,
                'motivo': 'cerrada',
                'fecha_cierre': timezone.localtime(pc.fecha_cierre),
            })

        # Correctitud efectiva: el juicio docente tiene precedencia sobre el
        # motor. `cohorte_est` ya viene resuelto del control de disponibilidad.
        ya_resuelto = esta_resuelto(usuario, ep, pc, cohorte_est)

        if not pc.desbloqueo_secuencial:
            # Modo libre: todos los ejercicios están abiertos, no hay gating por orden.
            puede_enviar = not ya_resuelto
        else:
            try:
                progreso = Progreso.objects.get(
                    estudiante=usuario, practica_comision=pc, cohorte=cohorte_est,
                )
                if progreso.ejercicio_practica_actual is None:
                    puede_enviar = not ya_resuelto
                elif ep.orden > progreso.ejercicio_practica_actual.orden:
                    return redirect('ejercicios:practica', pc_id=pc_id)
                else:
                    puede_enviar = not ya_resuelto
            except Progreso.DoesNotExist:
                first_ep = practica.ejercicio_practicas.order_by('orden').first()
                if first_ep and ep.pk == first_ep.pk:
                    puede_enviar = True
                else:
                    return redirect('ejercicios:practica', pc_id=pc_id)

    # Historial de intentos del estudiante para este ejercicio, acotado a su
    # cohorte: quien recursa no debe ver acá los intentos de su camada
    # anterior, ni que el formulario le precargue esa respuesta vieja.
    intentos = None
    if not (usuario.is_staff or usuario.es_docente):
        intentos = list(
            Intento.objects.filter(estudiante=usuario, ejercicio_practica=ep,
                                   practica_comision=pc, cohorte=cohorte_est)
            .order_by('-timestamp')
        )
    ultimo_intento = intentos[0] if intentos else None

    ejercicio = ep.ejercicio
    initial_formula_json = json.dumps('')
    initial_diccionario_json = json.dumps({})
    initial_enunciados_json = json.dumps([])
    initial_juicio_json = json.dumps(None)
    initial_valores_verdad_json = json.dumps({})
    initial_valor_verdad_json = json.dumps(None)

    if puede_enviar and ultimo_intento is not None:
        initial_diccionario_json = json.dumps(ultimo_intento.diccionario or {})
        if ejercicio.tipo == 'tabla_verdad':
            try:
                enunciados = json.loads(ultimo_intento.respuesta_raw)
                initial_enunciados_json = json.dumps(enunciados)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        elif ejercicio.tipo == 'determinacion_verdad':
            initial_formula_json = json.dumps(ultimo_intento.respuesta_raw)
            initial_valores_verdad_json = json.dumps(ultimo_intento.valores_verdad or {})
            initial_valor_verdad_json = json.dumps(ultimo_intento.valor_verdad_estudiante)
        else:
            initial_formula_json = json.dumps(ultimo_intento.respuesta_raw)

    # Pre-procesar intentos para mostrar argumentos en el historial
    if ejercicio.tipo == 'tabla_verdad' and intentos:
        for intento in intentos:
            try:
                intento.enunciados_parsed = json.loads(intento.respuesta_raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                intento.enunciados_parsed = None

    return render(request, 'ejercicios/ejercicio.html', {
        'ep': ep,
        'ejercicio': ejercicio,
        'pc': pc,
        'practica': practica,
        'puede_enviar': puede_enviar,
        'desbloqueo_secuencial': pc.desbloqueo_secuencial,
        'intentos': intentos,
        'ultimo_intento': ultimo_intento,
        'initial_formula_json': initial_formula_json,
        'initial_diccionario_json': initial_diccionario_json,
        'initial_enunciados_json': initial_enunciados_json,
        'initial_juicio_json': initial_juicio_json,
        'initial_valores_verdad_json': initial_valores_verdad_json,
        'initial_valor_verdad_json': initial_valor_verdad_json,
    })


@login_required
def mi_historial(request):
    """Muestra al estudiante autenticado su historial de intentos por ejercicio."""
    usuario = request.user
    if usuario.is_staff or usuario.es_docente:
        return redirect('docentes:comisiones_list')

    comisiones = (
        Comision.objects.filter(estudiantes=usuario)
        .order_by('nombre')
        .distinct()
    )

    comision_id = request.GET.get('comision')
    pc_id = request.GET.get('pc')
    context = build_historial_context(
        estudiante=usuario,
        comisiones=comisiones,
        comision_id=int(comision_id) if comision_id and comision_id.isdigit() else None,
        pc_id=int(pc_id) if pc_id and pc_id.isdigit() else None,
    )

    return render(request, 'docentes/estudiante_detail.html', {
        'estudiante': usuario,
        'vista_propia_estudiante': True,
        **context,
    })
