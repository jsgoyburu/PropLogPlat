"""Resolución de cohortes.

Módulo sin dependencias de vistas ni de la app ``ejercicios``, para que
``ejercicios`` pueda importarlo sin ciclo.
"""

from cursos.models import Cohorte, Inscripcion


def cohorte_activa():
    """La cohorte del cuatrimestre en curso, o ``None`` si no hay ninguna.

    El constraint ``unica_cohorte_activa`` garantiza que haya a lo sumo una.
    """
    return Cohorte.objects.filter(activa=True).first()


def cohorte_de(estudiante, comision):
    """Cohorte de ``estudiante`` en ``comision``, o ``None`` si no cursa ahí.

    Es la de su **inscripción más reciente** en esa comisión. Resuelve los dos
    casos de una sola regla:

    - Quien es de una camada anterior y sigue practicando para rendir el final
      acumula en su propia cohorte, no en la vigente.
    - Quien recursa tiene una inscripción nueva y acumula en la cohorte nueva,
      arrancando de cero.

    El desempate por ``-id`` cubre el caso de dos inscripciones con el mismo
    ``fecha_inscripcion`` (posible si se crean en el mismo request).
    """
    inscripcion = (
        Inscripcion.objects
        .filter(estudiante=estudiante, comision=comision)
        .order_by('-fecha_inscripcion', '-id')
        .first()
    )
    return inscripcion.cohorte if inscripcion else None
