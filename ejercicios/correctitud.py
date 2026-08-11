"""Definición única de la correctitud efectiva de un intento.

Un intento cuenta como correcto cuando el docente lo aprobó explícitamente, o
cuando el motor lo dio por correcto y el docente todavía no lo revisó. El juicio
docente tiene precedencia sobre el resultado del motor: un correcto rechazado
cuenta como incorrecto, y un incorrecto aprobado cuenta como correcto.

Este es el criterio que usan las analíticas, el servidor MCP y el panel docente.
No confundirlo con ``aprobado_docente=True`` a secas, que mide otra cosa: cuánto
revisó el docente a mano. En cursos masivos esa revisión no llega a todos los
intentos, así que no sirve como medida de avance.
"""

from django.db.models import Q

Q_CORRECTO = (
    Q(aprobado_docente=True)
    | Q(es_correcto=True, aprobado_docente__isnull=True)
)

Q_INCORRECTO = (
    Q(aprobado_docente=False)
    | Q(es_correcto=False, aprobado_docente__isnull=True)
)
