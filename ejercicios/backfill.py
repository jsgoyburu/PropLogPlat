"""Reglas de atribución del backfill de Progreso a PracticaComision.

Funciones puras que reciben las clases de modelo por parámetro, para que la
migración de datos las invoque con ``apps.get_model(...)`` (modelos históricos)
y los tests con los modelos reales, sin duplicar la regla en dos lados.

La atribución de ``Intento`` es el paso peligroso del cambio: si un intento
queda asignado a la comisión equivocada, ``eps_resueltos`` deja de contarlo y
el estudiante pierde un ejercicio que ya había resuelto. Por eso las reglas
exigen unicidad y devuelven ``None`` en vez de adivinar.
"""

from ejercicios.correctitud import Q_CORRECTO


def construir_indices(PracticaComision, Inscripcion):
    """Arma los dos mapas que necesitan las reglas, en dos queries.

    Args:
        PracticaComision: la clase del modelo (real o histórica).
        Inscripcion: la clase del modelo (real o histórica).

    Returns:
        tuple: ``(pcs_por_practica, comisiones_por_estudiante)`` donde
        ``pcs_por_practica`` mapea ``practica_id -> [(pc_id, comision_id), ...]``
        y ``comisiones_por_estudiante`` mapea ``estudiante_id -> {comision_id}``.
    """
    pcs_por_practica = {}
    for row in PracticaComision.objects.values('id', 'practica_id', 'comision_id'):
        pcs_por_practica.setdefault(row['practica_id'], []).append(
            (row['id'], row['comision_id'])
        )

    comisiones_por_estudiante = {}
    for row in Inscripcion.objects.values('estudiante_id', 'comision_id'):
        comisiones_por_estudiante.setdefault(row['estudiante_id'], set()).add(
            row['comision_id']
        )

    return pcs_por_practica, comisiones_por_estudiante


def pcs_candidatos(pcs_por_practica, comisiones_por_estudiante,
                   practica_id, estudiante_id):
    """PCs de ``practica_id`` en comisiones donde el estudiante está inscripto.

    Returns:
        list[int]: ids de PracticaComision, posiblemente vacía.
    """
    comisiones = comisiones_por_estudiante.get(estudiante_id, set())
    return [
        pc_id
        for pc_id, comision_id in pcs_por_practica.get(practica_id, [])
        if comision_id in comisiones
    ]


def pc_para_intento(pcs_por_practica, comisiones_por_estudiante,
                    practica_id, estudiante_id):
    """PracticaComision al que corresponde un intento, o ``None`` si es ambiguo.

    Reglas, en orden:

    1. PCs de la práctica donde el estudiante está inscripto: si hay
       exactamente uno, ése.
    2. Si no hay ninguno (estudiante desinscripto): PCs de la práctica en
       total, si hay exactamente uno.
    3. Si sigue ambiguo, ``None``.
    """
    candidatos = pcs_candidatos(
        pcs_por_practica, comisiones_por_estudiante, practica_id, estudiante_id,
    )
    if len(candidatos) == 1:
        return candidatos[0]

    if not candidatos:
        todos = pcs_por_practica.get(practica_id, [])
        if len(todos) == 1:
            return todos[0][0]

    return None


def atribuir_progreso(Progreso, EjercicioPractica, Intento, progreso, candidatos):
    """Resuelve un Progreso contra sus PracticaComision candidatos.

    Args:
        Progreso: la clase del modelo (real o histórica).
        EjercicioPractica: la clase del modelo (real o histórica).
        Intento: la clase del modelo (real o histórica).
        progreso: la instancia de Progreso a resolver, con ``practica_comision``
            todavía en NULL.
        candidatos (list[int]): ids de PracticaComision candidatos, como
            devuelve :func:`pcs_candidatos`.

    Reglas:

    1. Un solo candidato: se asigna el pc y el puntero se conserva verbatim.
    2. Ningún candidato (fila inalcanzable: práctica desasignada o estudiante
       desinscripto): se borra la fila.
    3. Dos o más candidatos: se abre en una fila por pc, con el puntero
       reconstruido desde los intentos ya atribuidos a cada uno. El modelo
       histórico (previo a la migración 0025) todavía exige ``practica`` como
       campo obligatorio, así que las filas nuevas lo completan solo cuando
       el modelo pasado lo tiene.

    Returns:
        str: ``'n1'``, ``'n0'`` o ``'n2'`` según la rama tomada.
    """
    if len(candidatos) == 1:
        progreso.practica_comision_id = candidatos[0]
        progreso.save(update_fields=['practica_comision'])
        return 'n1'

    if not candidatos:
        progreso.delete()
        return 'n0'

    tiene_practica = any(f.name == 'practica' for f in Progreso._meta.get_fields())
    tiene_cohorte = any(f.name == 'cohorte' for f in Progreso._meta.get_fields())
    for i, pc_id in enumerate(candidatos):
        ep_id = puntero_reconstruido(
            EjercicioPractica, Intento,
            progreso.estudiante_id, pc_id, progreso.practica_id,
        )
        if i == 0:
            progreso.practica_comision_id = pc_id
            progreso.ejercicio_practica_actual_id = ep_id
            progreso.save(update_fields=[
                'practica_comision', 'ejercicio_practica_actual',
            ])
        else:
            extra = {}
            if tiene_practica:
                extra['practica_id'] = progreso.practica_id
            if tiene_cohorte:
                extra['cohorte_id'] = progreso.cohorte_id
            Progreso.objects.create(
                estudiante_id=progreso.estudiante_id,
                practica_comision_id=pc_id,
                ejercicio_practica_actual_id=ep_id,
                **extra,
            )
    return 'n2'


def reatribuir_intento(pcs_por_practica, comisiones_por_estudiante,
                       practica_id, estudiante_id, pc_actual_id):
    """PracticaComision corregido para un intento que ya tiene uno asignado.

    La migración ``0015_practicacomision`` pobló ``Intento.practica_comision``
    con un mapa global ``practica_id -> PracticaComision``, quedándose con un pc
    arbitrario por práctica y sin mirar en qué comisión estaba inscripto el
    estudiante. Corrió además después de ``deduplicar_practicas``, que fusiona
    prácticas de comisiones distintas en una canónica. Un intento pudo quedar
    entonces apuntando a una comisión donde el estudiante nunca cursó, y al
    acotar el historial y las analíticas por ``practica_comision`` ese intento
    desaparecería de la comisión que corresponde.

    Returns:
        int | None: el pc corregido, o ``None`` si la atribución actual ya es
        consistente con la inscripción, o si no hay un único candidato con el
        que reemplazarla. Nunca devuelve algo que anule la FK: dejar el valor
        actual es preferible a romper la obligatoriedad que impone la 0026.
    """
    candidatos = pcs_candidatos(
        pcs_por_practica, comisiones_por_estudiante, practica_id, estudiante_id,
    )
    if pc_actual_id in candidatos:
        return None  # ya es coherente con la inscripción
    if len(candidatos) == 1:
        return candidatos[0]
    return None


def puntero_reconstruido(EjercicioPractica, Intento,
                         estudiante_id, pc_id, practica_id):
    """Primer EjercicioPractica por ``orden`` sin resolver en ese PracticaComision.

    Usa la correctitud efectiva (:data:`ejercicios.correctitud.Q_CORRECTO`): el
    juicio docente tiene precedencia sobre el motor. Es el mismo recálculo que
    hace ``avanzar_progreso`` en modo libre.

    Returns:
        int | None: id del EjercicioPractica, o ``None`` si están todos
        resueltos (práctica completa).
    """
    resueltos = set(
        Intento.objects
        .filter(Q_CORRECTO, estudiante_id=estudiante_id, practica_comision_id=pc_id)
        .values_list('ejercicio_practica_id', flat=True)
        .distinct()
    )
    siguiente = (
        EjercicioPractica.objects
        .filter(practica_id=practica_id)
        .exclude(pk__in=resueltos)
        .order_by('orden')
        .values_list('pk', flat=True)
        .first()
    )
    return siguiente
