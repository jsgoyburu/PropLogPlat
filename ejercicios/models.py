"""Modelos de la app ejercicios.

Contiene el banco de ejercicios, las prácticas, el progreso de los
estudiantes, y el registro de intentos de resolución.

Relaciones principales:
    - Un :class:`Ejercicio` puede pertenecer al banco propio del docente
      (``es_publico=False``) o al banco común (``es_publico=True``).
    - Una :class:`Practica` es una entidad canónica (título + ejercicios
      ordenados). Se asigna a una o más comisiones mediante
      :class:`PracticaComision`, que porta el orden, las fechas de
      disponibilidad y la FK a la comisión.
    - Un :class:`Progreso` registra hasta qué ejercicio llegó un estudiante
      en una práctica (tabla explícita para evitar recorrer todos los intentos).
    - Un :class:`Intento` registra cada envío de un estudiante.
"""

import logging

from django.conf import settings
from django.db import models
from django_ckeditor_5.fields import CKEditor5Field
from django.utils.translation import get_language

from cursos.models import Comision

logger = logging.getLogger(__name__)


def _texto_localizado(instancia, campo_base):
    """Devuelve una traducción disponible o conserva el castellano original."""
    idioma = (get_language() or 'es').split('-')[0]
    if idioma in {'en', 'fr', 'de'}:
        traduccion = getattr(instancia, f'{campo_base}_{idioma}', '')
        if traduccion:
            return traduccion
    return getattr(instancia, campo_base)


class Ejercicio(models.Model):
    """Un ejercicio de lógica proposicional.

    Puede ser de dos tipos: tabla de verdad (el estudiante construye la tabla
    a partir de una fórmula dada) o formalización (el estudiante escribe la
    fórmula a partir de un enunciado en lenguaje natural).

    La corrección se hace por equivalencia tabular entre la respuesta del
    estudiante y ``formula_solucion`` (ver :mod:`motor.verificador`).

    Attributes:
        enunciado (str): texto del ejercicio, puede incluir HTML para
            formato (negritas, subíndices, etc.).
        formula_solucion (str): fórmula en ASCII normalizado usada como
            referencia para la corrección.
        tipo (str): ``'tabla_verdad'`` o ``'formalizacion'``.
        creado_por (ForeignKey): docente o admin que creó el ejercicio.
            ``SET_NULL`` para conservar el ejercicio si el docente es
            eliminado del sistema.
        es_publico (bool): ``True`` → banco común accesible a todos los
            docentes. ``False`` → privado del docente creador.
        fecha_creacion (datetime): timestamp de creación (auto).

    Note:
        La limitación de corrección por equivalencia tabular (no detecta
        variables incorrectas, acepta tautologías equivalentes) está
        documentada en AGENTS.md §5 y en :func:`motor.verificador.verificar`.
    """

    TIPO_CHOICES = [
        ('tabla_verdad', 'Tabla de verdad'),
        ('formalizacion', 'Formalización'),
        ('determinacion_verdad', 'Determinación de valor de verdad'),
    ]

    enunciado = models.TextField(
        verbose_name='enunciado',
        help_text='Texto del ejercicio. Puede incluir HTML básico.',
    )
    enunciado_en = models.TextField(
        blank=True,
        default='',
        verbose_name='enunciado en inglés',
        help_text='Traducción opcional. Si queda vacía se mostrará el castellano original.',
    )
    enunciado_fr = models.TextField(
        blank=True,
        default='',
        verbose_name='enunciado en francés',
        help_text='Traducción opcional. Si queda vacía se mostrará el castellano original.',
    )
    enunciado_de = models.TextField(
        blank=True,
        default='',
        verbose_name='enunciado en alemán',
        help_text='Traducción opcional. Si queda vacía se mostrará el castellano original.',
    )
    formula_solucion = models.CharField(
        max_length=500,
        verbose_name='fórmula solución',
        help_text=(
            'Fórmula en ASCII normalizado: ~ . & | -> <-> '
            'Ejemplo: p -> (q . ~r)'
        ),
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        verbose_name='tipo',
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ejercicios_creados',
        verbose_name='creado por',
    )
    es_publico = models.BooleanField(
        default=False,
        verbose_name='banco común',
        help_text=(
            'Si está marcado, el ejercicio es visible a todos los docentes '
            '(banco común). Si no, es privado del docente creador.'
        ),
    )
    diccionario_solucion = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='diccionario solución',
        help_text='Diccionario de variables usado por el docente al crear el ejercicio.',
    )
    valores_verdad_solucion = models.JSONField(
        null=True,
        blank=True,
        default=None,
        verbose_name='valores de verdad solución',
        help_text=(
            'Solo para ejercicios de determinación de verdad. '
            'Mapa {letra: bool} con el valor de verdad asignado a cada variable. '
            'Ej: {"A": true, "B": false}.'
        ),
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='fecha de creación',
    )

    class Meta:
        verbose_name = 'ejercicio'
        verbose_name_plural = 'ejercicios'
        ordering = ['-fecha_creacion']

    def __str__(self) -> str:
        publico = ' [público]' if self.es_publico else ''
        return f'[{self.get_tipo_display()}]{publico} {self.enunciado[:60]}'

    @property
    def enunciado_localizado(self):
        return _texto_localizado(self, 'enunciado')

    @property
    def tipo_localizado(self):
        idioma = (get_language() or 'es').split('-')[0]
        etiquetas = {
            'tabla_verdad': {
                'es': 'Tabla de verdad', 'en': 'Truth table',
                'fr': 'Table de vérité', 'de': 'Wahrheitstafel',
            },
            'formalizacion': {
                'es': 'Formalización', 'en': 'Formalization',
                'fr': 'Formalisation', 'de': 'Formalisierung',
            },
            'determinacion_verdad': {
                'es': 'Determinación de valor de verdad', 'en': 'Truth-value determination',
                'fr': 'Détermination de la valeur de vérité', 'de': 'Bestimmung des Wahrheitswerts',
            },
        }
        return etiquetas.get(self.tipo, {}).get(idioma, self.get_tipo_display())


class Practica(models.Model):
    """Una práctica es una entidad canónica: título + conjunto ordenado de ejercicios.

    Una misma práctica puede asignarse a múltiples comisiones a través de
    :class:`PracticaComision`, que porta el orden, las fechas de disponibilidad
    y la FK a la comisión específica.

    El patrón copy-on-write se gestiona mediante ``practica_origen``: cuando
    una práctica importada es modificada en el contexto de una comisión, se
    crea una nueva :class:`Practica` y ``practica_origen`` se limpia.

    Attributes:
        titulo (str): nombre descriptivo, p.ej. "Práctica 1 – Tablas".
        descripcion (CKEditor5Field): descripción opcional, visible para estudiantes.
        es_publica (bool): si está en el banco común de prácticas importables.
        creada_por (ForeignKey): docente o admin que creó la práctica.
        practica_origen (ForeignKey self): si fue importada, apunta al original.
        ejercicios (ManyToMany via EjercicioPractica): ejercicios en orden.
    """

    titulo = models.CharField(
        max_length=200,
        verbose_name='título',
        help_text='Ejemplo: "Práctica 1 – Tablas de verdad".',
    )
    titulo_en = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='título en inglés',
    )
    titulo_fr = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='título en francés',
    )
    titulo_de = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='título en alemán',
    )
    descripcion = CKEditor5Field(
        null=True,
        blank=True,
        verbose_name='descripción',
        config_name='extends',
        help_text='Descripción opcional de la práctica, visible para los estudiantes. Puede incluir formato (negritas, listas, etc.).',
    )
    descripcion_en = CKEditor5Field(
        null=True,
        blank=True,
        verbose_name='descripción en inglés',
        config_name='extends',
    )
    descripcion_fr = CKEditor5Field(
        null=True,
        blank=True,
        verbose_name='descripción en francés',
        config_name='extends',
    )
    descripcion_de = CKEditor5Field(
        null=True,
        blank=True,
        verbose_name='descripción en alemán',
        config_name='extends',
    )
    es_publica = models.BooleanField(
        default=False,
        verbose_name='banco común',
        help_text=(
            'Si está marcado, la práctica (con todos sus ejercicios) es visible '
            'a todos los docentes para ser importada a sus comisiones.'
        ),
    )
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='practicas_creadas',
        verbose_name='creada por',
    )
    ejercicios = models.ManyToManyField(
        Ejercicio,
        through='EjercicioPractica',
        verbose_name='ejercicios',
        blank=True,
    )
    practica_origen = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='derivadas',
        verbose_name='importada desde',
        help_text=(
            'Si esta práctica fue importada desde otra, apunta al original. '
            'Se limpia automáticamente cuando la práctica es modificada (copy-on-write).'
        ),
    )

    class Meta:
        verbose_name = 'práctica'
        verbose_name_plural = 'prácticas'
        ordering = ['titulo']
        indexes = [
            models.Index(fields=['practica_origen'], name='practica_origen_idx'),
        ]

    def __str__(self) -> str:
        return self.titulo

    @property
    def titulo_localizado(self):
        return _texto_localizado(self, 'titulo')

    @property
    def descripcion_localizada(self):
        return _texto_localizado(self, 'descripcion')


class PracticaComision(models.Model):
    """Tabla intermedia que asigna una Practica a una Comision.

    Análoga a :class:`EjercicioPractica` (que asigna un Ejercicio a una
    Practica), esta tabla porta los atributos específicos del contexto de
    cursado: orden dentro de la comisión, y ventana de disponibilidad
    (fechas de apertura y cierre).

    Attributes:
        practica (ForeignKey): la práctica canónica.
        comision (ForeignKey): la comisión a la que se asigna.
        orden (int): posición de la práctica dentro de la comisión (1, 2, 3…).
            Junto con ``comision``, forma una clave única.
        fecha_apertura (datetime): opcional, inicio del período de acceso.
        fecha_cierre (datetime): opcional, fin del período de acceso.
    """

    practica = models.ForeignKey(
        Practica,
        on_delete=models.CASCADE,
        related_name='practicas_comisiones',
        verbose_name='práctica',
    )
    comision = models.ForeignKey(
        Comision,
        on_delete=models.CASCADE,
        related_name='practicas_comisiones',
        verbose_name='comisión',
    )
    orden = models.PositiveIntegerField(
        verbose_name='orden',
        help_text='Orden de la práctica dentro de la comisión (1, 2, 3…).',
    )
    fecha_apertura = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='apertura',
        help_text='Opcional. Si se indica, los estudiantes no pueden acceder antes de esta fecha y hora.',
    )
    fecha_cierre = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='cierre',
        help_text='Opcional. Si se indica, los estudiantes no pueden acceder después de esta fecha y hora.',
    )
    desbloqueo_secuencial = models.BooleanField(
        default=True,
        verbose_name='desbloqueo secuencial',
        help_text=(
            'Si está marcado, cada ejercicio se habilita al resolver correctamente '
            'el anterior. Si no, todos los ejercicios están disponibles desde el inicio.'
        ),
    )

    class Meta:
        verbose_name = 'práctica en comisión'
        verbose_name_plural = 'prácticas en comisiones'
        ordering = ['orden']
        unique_together = ['comision', 'orden']

    def __str__(self) -> str:
        return f'{self.comision} – {self.practica.titulo} (orden {self.orden})'

    def disponible_para_estudiante(self) -> bool:
        """Devuelve True si la práctica está dentro del período de acceso."""
        from django.utils import timezone
        ahora = timezone.now()
        if self.fecha_apertura and ahora < self.fecha_apertura:
            return False
        if self.fecha_cierre and ahora > self.fecha_cierre:
            return False
        return True

    def estado_disponibilidad(self) -> str:
        """Devuelve 'abierta', 'no_iniciada' o 'cerrada'."""
        from django.utils import timezone
        ahora = timezone.now()
        if self.fecha_apertura and ahora < self.fecha_apertura:
            return 'no_iniciada'
        if self.fecha_cierre and ahora > self.fecha_cierre:
            return 'cerrada'
        return 'abierta'


class EjercicioPractica(models.Model):
    """Tabla intermedia que ordena los ejercicios dentro de una práctica.

    El campo ``orden`` fija la secuencia de presentación. Si la práctica está
    en modo secuencial en esa comisión (``PracticaComision.desbloqueo_secuencial``),
    además determina el desbloqueo: para avanzar al ejercicio N+1 hay que
    resolver correctamente el N. En modo libre sólo define el orden de la lista.

    Attributes:
        practica (ForeignKey): la práctica que contiene este ejercicio.
        ejercicio (ForeignKey): el ejercicio.
        orden (int): posición dentro de la práctica (1, 2, 3…).
            Junto con ``practica``, forma una clave única.
    """

    practica = models.ForeignKey(
        Practica,
        on_delete=models.CASCADE,
        related_name='ejercicio_practicas',
        verbose_name='práctica',
    )
    ejercicio = models.ForeignKey(
        Ejercicio,
        on_delete=models.CASCADE,
        related_name='ejercicio_practicas',
        verbose_name='ejercicio',
    )
    orden = models.PositiveIntegerField(
        verbose_name='orden',
        help_text='Posición dentro de la práctica (1, 2, 3…).',
    )

    class Meta:
        verbose_name = 'ejercicio en práctica'
        verbose_name_plural = 'ejercicios en prácticas'
        ordering = ['orden']
        unique_together = ['practica', 'orden']

    def __str__(self) -> str:
        return f'{self.practica} – Ej. {self.orden}: {self.ejercicio}'


class Intento(models.Model):
    """Registro de un intento de resolución de un ejercicio por un estudiante.

    Se crea un intento por cada envío, independientemente de si es correcto
    o incorrecto. Esto permite al docente ver el historial completo y
    calcular tasas de acierto por ejercicio.

    Attributes:
        estudiante (ForeignKey): el usuario que envió la respuesta.
        ejercicio_practica (ForeignKey): el :class:`EjercicioPractica`
            al que corresponde el intento (identifica práctica + ejercicio
            + posición).
        practica_comision (ForeignKey): el :class:`PracticaComision`
            que identifica en qué comisión se realizó el intento.
            Invariante: ``practica_comision.practica == ejercicio_practica.practica``.
        respuesta_raw (str): la fórmula tal como la envió el estudiante,
            en ASCII normalizado.
        es_correcto (bool): resultado de la comparación tabular.
        timestamp (datetime): momento del intento (auto).
    """

    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='intentos',
        verbose_name='estudiante',
    )
    ejercicio_practica = models.ForeignKey(
        EjercicioPractica,
        on_delete=models.CASCADE,
        related_name='intentos',
        verbose_name='ejercicio en práctica',
    )
    practica_comision = models.ForeignKey(
        PracticaComision,
        on_delete=models.CASCADE,
        related_name='intentos',
        verbose_name='práctica en comisión',
    )
    cohorte = models.ForeignKey(
        'cursos.Cohorte',
        on_delete=models.PROTECT,
        related_name='intentos',
        verbose_name='cohorte',
    )
    respuesta_raw = models.CharField(
        max_length=2000,
        verbose_name='respuesta',
        help_text='Fórmula enviada por el estudiante en ASCII normalizado, o JSON del argumento para ejercicios de tabla de verdad.',
    )
    es_correcto = models.BooleanField(
        verbose_name='es correcto',
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name='fecha y hora',
    )
    comentario_docente = models.TextField(
        null=True,
        blank=True,
        default='',
        verbose_name='comentario docente',
        help_text='Comentario opcional del docente/admin sobre este intento.',
    )
    aprobado_docente = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name='aprobación docente',
        help_text=(
            'None = pendiente de revisión, '
            'True = aprobado por docente, '
            'False = rechazado por docente.'
        ),
    )
    diccionario = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='diccionario de variables',
        help_text='Mapa {letra: proposición} construido por el estudiante. Ej: {"A": "Llueve", "B": "Hay tráfico"}.',
    )
    tabla_json = models.JSONField(
        null=True,
        blank=True,
        default=None,
        verbose_name='tabla de verdad',
        help_text='Tabla completada por el estudiante en ejercicios de tabla de verdad. '
                  'Lista de filas: [{"A": true, "B": false, "P1": true, "C": false}, ...].',
    )
    valores_verdad = models.JSONField(
        null=True,
        blank=True,
        default=None,
        verbose_name='valores de verdad del diccionario',
        help_text=(
            'Solo para ejercicios de determinación de verdad. '
            'Mapa {letra: bool} con el valor de verdad asignado por el estudiante a cada variable. '
            'Ej: {"A": true, "B": false}.'
        ),
    )
    valor_verdad_estudiante = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name='valor de verdad asignado',
        help_text=(
            'Solo para ejercicios de determinación de verdad. '
            'Valor de verdad que el estudiante declaró para su fórmula (V o F).'
        ),
    )
    juicio_estudiante = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name='juicio de validez del estudiante',
        help_text=(
            'Solo para ejercicios de tabla de verdad. '
            'True = el estudiante declaró el argumento como válido, '
            'False = inválido, None = no indicado.'
        ),
    )

    ERROR_CATEGORIA_CHOICES = [
        # ── Formalización ─────────────────────────────────────────────────
        ('tautologia', 'Tautología espuria (siempre verdadero)'),
        ('contradiccion', 'Contradicción (siempre falso)'),
        ('polaridad', 'Polaridad (negación exacta de la solución)'),
        ('mas_fuerte', 'Más fuerte: solución implica estudiante, no al revés'),
        ('mas_debil', 'Más débil: estudiante implica solución, no al revés'),
        ('equivalente_alt', 'Formalización alternativa válida (revisar)'),
        ('error_parcial_1', 'Error parcial — 1 fila distinta'),
        ('error_parcial_2', 'Error parcial — 2 filas distintas'),
        ('error_sistemico', 'Error sistémico (más de la mitad de filas distintas)'),
        ('variables_extra', 'Variables extra (más variables que la solución)'),
        ('variables_menos', 'Variables insuficientes (menos variables que la solución)'),
        ('sin_clasificar', 'Sin clasificar'),
        # ── Tabla de verdad ───────────────────────────────────────────────
        ('juicio', 'Error solo en juicio de validez (tabla correcta, juicio incorrecto)'),
        ('columna_premisa', 'Error en columna de premisa'),
        ('columna_conclusion', 'Error en columna de conclusión'),
        # ── Otros ─────────────────────────────────────────────────────────
        ('error_parse', 'Error de parseo (fórmula no válida)'),
        ('otro', 'Otro / no clasificado'),
    ]
    error_categoria = models.CharField(
        max_length=30,
        choices=ERROR_CATEGORIA_CHOICES,
        null=True,
        blank=True,
        default=None,
        verbose_name='categoría de error',
        help_text=(
            'Categoría del error lógico. Calculada offline por el management command '
            'calcular_categorias_error. Null = aún no procesado o intento correcto.'
        ),
    )
    REVISION_DICCIONARIO_CHOICES = [
        ('', 'Sin revisar (no aplica o Groq no disponible)'),
        ('pasa', 'Pasa — Groq aprobó el diccionario'),
        ('revisar', 'Revisar — Groq sugiere revisión docente'),
    ]
    revision_diccionario = models.CharField(
        max_length=10,
        choices=REVISION_DICCIONARIO_CHOICES,
        blank=True,
        default='',
        verbose_name='revisión del diccionario',
        help_text=(
            'Resultado de la revisión automática del diccionario por Groq (solo intentos '
            'correctos con diccionario). Vacío = no aplica o Groq no disponible.'
        ),
    )

    class Meta:
        verbose_name = 'intento'
        verbose_name_plural = 'intentos'
        ordering = ['-timestamp']
        indexes = [
            models.Index(
                fields=['estudiante', 'ejercicio_practica'],
                name='intento_est_ep_idx',
            ),
            models.Index(
                fields=['es_correcto', 'aprobado_docente'],
                name='intento_correcto_aprobado_idx',
            ),
            models.Index(
                fields=['aprobado_docente'],
                name='intento_aprobado_idx',
            ),
        ]

    def __str__(self) -> str:
        estado = '✓' if self.es_correcto else '✗'
        return (
            f'{estado} {self.estudiante} | '
            f'{self.ejercicio_practica} | '
            f'{self.timestamp:%Y-%m-%d %H:%M}'
        )


class Progreso(models.Model):
    """Registra hasta qué ejercicio llegó un estudiante en una práctica.

    Una fila por terna ``(estudiante, practica_comision, cohorte)``: el
    progreso es del cursado **de una camada**. Quien recursa la misma
    comisión en otra cohorte arranca con una fila nueva y su progreso
    anterior queda intacto. Una misma :class:`Practica` asignada a
    dos comisiones tiene una fila en cada una, con su propio modo de desbloqueo
    y su propio puntero. El campo ``ejercicio_practica_actual`` apunta al último
    ejercicio desbloqueado; cuando vale ``None``, la práctica está completa.

    Tabla explícita (no calculada desde :class:`Intento`) para evitar
    recorrer todos los intentos en cada request (AGENTS.md §10).

    El modo lo define ``PracticaComision.desbloqueo_secuencial``, así que una
    misma práctica puede comportarse distinto en dos comisiones. La lógica de
    avance vive en :mod:`ejercicios.progreso`.

    Modo **secuencial** (default):
        - El primer ejercicio de cada práctica está desbloqueado para todos
          los estudiantes de la comisión desde que la práctica existe.
        - Al recibir un intento correcto en ``ejercicio_practica_actual``,
          el progreso avanza al siguiente :class:`EjercicioPractica` por
          ``orden``. Si no hay siguiente, ``ejercicio_practica_actual``
          pasa a ``None`` (práctica completada).
        - Si no existe aún un :class:`Progreso` para el par, se crea
          apuntando al primer ejercicio en el primer intento.

    Modo **libre**:
        - Todos los ejercicios están disponibles desde el inicio.
        - ``ejercicio_practica_actual`` se recalcula como el primero sin
          resolver, así que deja de significar "hasta dónde llegó" y pasa a
          significar "qué le falta". Se mantiene actualizado para que cambiar
          de modo a mitad de cursada no deje datos inconsistentes.

    Attributes:
        estudiante (ForeignKey): el estudiante.
        practica_comision (ForeignKey): la asignación de la práctica a la
            comisión desde la que el estudiante la está cursando.
        ejercicio_practica_actual (ForeignKey, nullable): el
            :class:`EjercicioPractica` actualmente desbloqueado.
            ``None`` significa práctica completada.
    """

    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='progresos',
        verbose_name='estudiante',
    )
    practica_comision = models.ForeignKey(
        PracticaComision,
        on_delete=models.CASCADE,
        related_name='progresos',
        verbose_name='práctica en comisión',
    )
    cohorte = models.ForeignKey(
        'cursos.Cohorte',
        on_delete=models.PROTECT,
        related_name='progresos',
        verbose_name='cohorte',
    )
    ejercicio_practica_actual = models.ForeignKey(
        EjercicioPractica,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='progresos_actuales',
        verbose_name='ejercicio actual',
        help_text='Null = práctica completada.',
    )

    class Meta:
        verbose_name = 'progreso'
        verbose_name_plural = 'progresos'
        unique_together = ['estudiante', 'practica_comision', 'cohorte']

    def __str__(self) -> str:
        if self.ejercicio_practica_actual is None:
            estado = 'completada'
        else:
            estado = f'en ej. {self.ejercicio_practica_actual.orden}'
        return f'{self.estudiante} | {self.practica_comision} | {estado}'
