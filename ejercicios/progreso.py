"""Avance del :class:`~ejercicios.models.Progreso` de un estudiante en una práctica.

Centraliza la lógica que antes estaba duplicada en ``ejercicios/api/views.py``
(intento correcto del estudiante) y en ``docentes/views.py`` (aprobación manual
de un intento incorrecto).

El progreso es **por cursado, no por práctica canónica**: la clave es
``(estudiante, practica_comision)``. Una misma :class:`Practica` asignada a dos
comisiones tiene una fila de progreso en cada una, con su propio modo de
desbloqueo y su propio puntero.

Hay dos modos, definidos por ``PracticaComision.desbloqueo_secuencial``:

- **secuencial**: el progreso avanza al siguiente ejercicio por ``orden`` sólo
  cuando el estudiante resuelve el que tiene desbloqueado.
- **libre**: todos los ejercicios están disponibles, así que el "actual" se
  recalcula como el primero sin resolver. Sin este recálculo, un estudiante que
  resuelve fuera de orden dejaría el progreso clavado en el primer ejercicio y
  la práctica nunca se marcaría completa.
"""

from django.db import transaction

from ejercicios.correctitud import Q_CORRECTO
from ejercicios.models import EjercicioPractica, Intento, Progreso


def eps_resueltos(estudiante, pc, cohorte) -> set[int]:
    """Ids de los EjercicioPractica ya resueltos por ``estudiante`` en ``pc``.

    Acota por ``practica_comision`` y por ``cohorte``: ni lo resuelto en otra
    comisión que comparta la práctica canónica, ni lo resuelto en una camada
    anterior de esta misma comisión, cuenta acá.

    Usa la correctitud efectiva de :mod:`ejercicios.correctitud`: el juicio
    docente tiene precedencia sobre el resultado del motor.
    """
    return set(
        Intento.objects
        .filter(Q_CORRECTO, estudiante=estudiante, practica_comision=pc, cohorte=cohorte)
        .values_list('ejercicio_practica_id', flat=True)
        .distinct()
    )


def esta_resuelto(estudiante, ep, pc, cohorte) -> bool:
    """True si ``estudiante`` resolvió ``ep`` en ``pc`` dentro de ``cohorte``."""
    return (
        Intento.objects
        .filter(Q_CORRECTO, estudiante=estudiante, ejercicio_practica=ep,
                practica_comision=pc, cohorte=cohorte)
        .exists()
    )


def avanzar_progreso(estudiante, ep, pc, cohorte) -> tuple[bool, int]:
    """Actualiza el Progreso de ``estudiante`` en ``pc`` tras resolverse ``ep``.

    Args:
        estudiante: el usuario estudiante.
        ep: el :class:`~ejercicios.models.EjercicioPractica` recién resuelto.
        pc: el :class:`~ejercicios.models.PracticaComision` desde el que se
            resolvió. Define el modo de desbloqueo y la fila de progreso.
        cohorte: la :class:`~cursos.models.Cohorte` del estudiante en esa
            comisión. Define qué fila de progreso se avanza: quien recursa
            tiene una fila por camada.

    Returns:
        tuple[bool, int]: ``(practica_completa, ejercicios_pendientes)``.

    Raises:
        ValueError: si ``pc`` no corresponde a la práctica de ``ep``.
    """
    if pc.practica_id != ep.practica_id:
        raise ValueError(
            f'PracticaComision {pc.pk} (práctica {pc.practica_id}) no corresponde '
            f'al EjercicioPractica {ep.pk} (práctica {ep.practica_id}).'
        )

    secuencial = pc.desbloqueo_secuencial
    practica_id = pc.practica_id
    total = EjercicioPractica.objects.filter(practica_id=practica_id).count()

    with transaction.atomic():
        # Lock pesimista: evita la race condition entre dos requests simultáneos
        # sobre el mismo (estudiante, practica_comision).
        progreso = (
            Progreso.objects
            .select_for_update()
            .filter(estudiante=estudiante, practica_comision=pc, cohorte=cohorte)
            .first()
        )
        if progreso is None:
            progreso, _ = Progreso.objects.get_or_create(
                estudiante=estudiante,
                practica_comision=pc,
                cohorte=cohorte,
                defaults={'ejercicio_practica_actual': ep},
            )
            progreso = (
                Progreso.objects
                .select_for_update()
                .get(estudiante=estudiante, practica_comision=pc, cohorte=cohorte)
            )

        if secuencial:
            if progreso.ejercicio_practica_actual == ep:
                siguiente = (
                    EjercicioPractica.objects
                    .filter(practica_id=practica_id, orden__gt=ep.orden)
                    .order_by('orden')
                    .first()
                )
                progreso.ejercicio_practica_actual = siguiente
                progreso.save(update_fields=['ejercicio_practica_actual'])
            actual = progreso.ejercicio_practica_actual
            # En secuencial, todo lo anterior al actual está resuelto.
            pendientes = 0 if actual is None else total - actual.orden + 1
        else:
            resueltos = eps_resueltos(estudiante, pc, cohorte)
            siguiente = (
                EjercicioPractica.objects
                .filter(practica_id=practica_id)
                .exclude(pk__in=resueltos)
                .order_by('orden')
                .first()
            )
            progreso.ejercicio_practica_actual = siguiente
            progreso.save(update_fields=['ejercicio_practica_actual'])
            pendientes = total - len(resueltos)

    return progreso.ejercicio_practica_actual is None, max(pendientes, 0)
