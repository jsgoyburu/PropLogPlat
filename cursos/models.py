"""Modelos de la app cursos.

Gestiona la estructura organizativa de la plataforma: comisiones y la
relación de inscripción de estudiantes a ellas.

Una **comisión** es la unidad pedagógica mínima: un grupo de estudiantes
asignado a uno o más docentes, con un conjunto de prácticas ordenadas.
Equivale a una "clase" o "turno" en el contexto de IPC/CBC-UBA.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q


class Cohorte(models.Model):
    """Una camada de estudiantes: el cuatrimestre en que cursan.

    Es global a la plataforma, no por comisión: hay un solo cuatrimestre en
    curso. Una comisión recibe cohortes sucesivas conservando sus prácticas y
    el historial de las camadas anteriores.

    La cohorte es la **camada de pertenencia**, no el período del calendario:
    quien es de 2026-C1 y sigue practicando en septiembre para rendir el final
    acumula en 2026-C1, no en la cohorte vigente ese mes.

    Attributes:
        anio (int): año calendario, p.ej. 2026.
        cuatrimestre (int): 1 ó 2.
        activa (bool): si es el cuatrimestre en curso. Solo puede haber una.
            No controla acceso: estudiantes de camadas anteriores siguen
            entrando. Define en qué cohorte abre el panel y a cuál se inscribe
            por defecto.
    """

    CUATRIMESTRE_CHOICES = [(1, '1º'), (2, '2º')]

    anio = models.PositiveIntegerField(verbose_name='año')
    cuatrimestre = models.PositiveSmallIntegerField(
        choices=CUATRIMESTRE_CHOICES,
        verbose_name='cuatrimestre',
    )
    activa = models.BooleanField(
        default=False,
        verbose_name='cohorte activa',
        help_text='El cuatrimestre en curso. Solo puede haber una activa.',
    )

    class Meta:
        verbose_name = 'cohorte'
        verbose_name_plural = 'cohortes'
        unique_together = ['anio', 'cuatrimestre']
        ordering = ['-anio', '-cuatrimestre']
        constraints = [
            models.UniqueConstraint(
                fields=['activa'],
                condition=Q(activa=True),
                name='unica_cohorte_activa',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.anio} – C{self.cuatrimestre}'


class Comision(models.Model):
    """Una comisión agrupa estudiantes bajo uno o más docentes.

    Los docentes asignados a la comisión pueden crear y gestionar sus
    prácticas. Los estudiantes acceden a las prácticas de su comisión
    mediante la relación :class:`Inscripcion`.

    Attributes:
        nombre (str): nombre descriptivo, p.ej. "IPC – Turno Noche 2025".
        docentes (ManyToMany): docentes a cargo. Solo usuarios con
            ``es_docente=True`` pueden ser asignados.
        estudiantes (ManyToMany via Inscripcion): estudiantes inscriptos.
    """

    TIPO_ENCUESTA_CHOICES = [
        ('completa', 'Completa (datos básicos + 3 consentimientos + encuesta socioeducativa)'),
        ('basica', 'Básica (datos básicos + consentimiento pedagógico)'),
    ]

    nombre = models.CharField(
        max_length=100,
        verbose_name='nombre',
        help_text='Ejemplo: "IPC – Turno Noche 2025".',
    )
    tipo_encuesta = models.CharField(
        max_length=10,
        choices=TIPO_ENCUESTA_CHOICES,
        default='completa',
        verbose_name='tipo de encuesta de onboarding',
        help_text=(
            'Determina si el onboarding incluye la encuesta socioeducativa completa '
            'o solo los datos básicos y el consentimiento pedagógico.'
        ),
    )
    docentes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        limit_choices_to={'es_docente': True},
        related_name='comisiones',
        verbose_name='docentes',
        blank=True,
    )
    estudiantes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='Inscripcion',
        limit_choices_to={'es_docente': False, 'is_staff': False},
        related_name='comisiones_inscripto',
        verbose_name='estudiantes',
        blank=True,
    )

    class Meta:
        verbose_name = 'comisión'
        verbose_name_plural = 'comisiones'
        ordering = ['nombre']

    def __str__(self) -> str:
        return self.nombre


class Inscripcion(models.Model):
    """Tabla intermedia que registra la inscripción de un estudiante a una comisión.

    Usar la tabla through explícita permite agregar metadatos a la relación
    (p.ej. ``fecha_inscripcion``) y habilita queries directas sobre inscripciones.

    Attributes:
        estudiante (ForeignKey): el usuario estudiante inscripto.
        comision (ForeignKey): la comisión en la que está inscripto.
        fecha_inscripcion (datetime): fecha y hora de inscripción (auto).
    """

    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='inscripciones',
        verbose_name='estudiante',
    )
    comision = models.ForeignKey(
        Comision,
        on_delete=models.CASCADE,
        related_name='inscripciones',
        verbose_name='comisión',
    )
    cohorte = models.ForeignKey(
        'Cohorte',
        on_delete=models.PROTECT,
        related_name='inscripciones',
        verbose_name='cohorte',
    )
    fecha_inscripcion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='fecha de inscripción',
    )

    class Meta:
        verbose_name = 'inscripción'
        verbose_name_plural = 'inscripciones'
        unique_together = ['estudiante', 'comision', 'cohorte']
        ordering = ['comision', 'estudiante']

    def __str__(self) -> str:
        return f'{self.estudiante} en {self.comision}'


class Parcial(models.Model):
    """Instancia de evaluación parcial de lógica para una comisión.

    Cada comisión puede tener múltiples parciales (Parcial 1, Recuperatorio, etc.).
    Al crear un Parcial, se pre-crean NotaParcial(puntaje=null) para todos los
    estudiantes inscriptos en ese momento.
    """

    comision = models.ForeignKey(
        Comision,
        on_delete=models.CASCADE,
        related_name='parciales',
        verbose_name='comisión',
    )
    cohorte = models.ForeignKey(
        'Cohorte',
        on_delete=models.PROTECT,
        related_name='parciales',
        verbose_name='cohorte',
    )
    nombre = models.CharField(
        max_length=100,
        verbose_name='nombre',
        help_text='Ej: "Parcial 1", "Recuperatorio".',
    )
    fecha = models.DateField(verbose_name='fecha')
    puntaje_total = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='puntaje total (parte lógica)',
        help_text='Máximo posible de la parte de lógica.',
    )
    umbral_aprobacion = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=4.00,
        verbose_name='umbral aprobación (sobre 10)',
        help_text='Nota mínima normalizada (0-10) para aprobar. Default 4.00, igual que la serie histórica.',
    )
    umbral_promocion = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=7.00,
        verbose_name='umbral promoción (sobre 10)',
        help_text='Nota mínima normalizada (0-10) para promocionar. Default 7.00, igual que la serie histórica.',
    )

    class Meta:
        verbose_name = 'parcial'
        verbose_name_plural = 'parciales'
        ordering = ['fecha', 'nombre']

    def __str__(self) -> str:
        return f'{self.nombre} — {self.comision}'


class NotaParcial(models.Model):
    """Nota de un estudiante en la parte de lógica de un parcial.

    puntaje=null significa que aún no fue cargada.
    """

    parcial = models.ForeignKey(
        Parcial,
        on_delete=models.CASCADE,
        related_name='notas',
        verbose_name='parcial',
    )
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notas_parciales',
        verbose_name='estudiante',
    )
    puntaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='puntaje',
    )
    ausente = models.BooleanField(
        default=False,
        verbose_name='ausente al parcial',
        help_text='Marcar si el estudiante no se presentó. Cuando es True, puntaje y nota_logica_parcial deben ser null.',
    )
    nota_logica_parcial = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='nota sección lógica',
        help_text='Puntaje de la sección de lógica del parcial (subconjunto del puntaje global).',
    )

    class Meta:
        verbose_name = 'nota de parcial'
        verbose_name_plural = 'notas de parcial'
        unique_together = ['parcial', 'estudiante']
        ordering = ['estudiante__last_name', 'estudiante__first_name', 'estudiante__username']

    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        if self.ausente and self.puntaje is not None:
            errors['puntaje'] = 'Debe ser null si el estudiante está ausente.'
        if self.ausente and self.nota_logica_parcial is not None:
            errors['nota_logica_parcial'] = 'Debe ser null si el estudiante está ausente.'
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f'{self.estudiante} — {self.parcial}: {self.puntaje}'
