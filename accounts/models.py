"""Modelos de la app accounts.

Extiende el modelo de usuario de Django con el campo ``es_docente``
para distinguir entre los dos roles no-admin de la plataforma.

Roles:
    - **Admin** (``is_staff=True``): superusuario Django. Edita/elimina
      cualquier ejercicio del banco común y gestiona usuarios.
    - **Docente** (``es_docente=True``): crea ejercicios, arma prácticas,
      gestiona comisiones, ve analíticas.
    - **Estudiante** (``es_docente=False``, ``is_staff=False``): accede
      a las prácticas de su comisión y resuelve ejercicios.

Nota de diseño:
    El alta de estudiantes puede ocurrir por dos vías: creación docente o
    auto-registro guiado desde un link de comisión. En ambos casos el
    acceso queda acotado a comisiones existentes y explícitas.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class ConfigSitio(models.Model):
    """Configuración global del sitio (singleton).

    Solo puede existir una fila. Desde el admin se puede editar
    el nombre del sitio y los colores principales.
    """

    IDIOMA_CHOICES = [
        ('es', 'Castellano'),
        ('en', 'English'),
        ('fr', 'Français'),
        ('de', 'Deutsch'),
    ]

    nombre_sitio = models.CharField(
        max_length=100,
        default='PropLogPlat',
        verbose_name='nombre del sitio',
    )
    color_primario = models.CharField(
        max_length=7,
        default='#1a1a2e',
        verbose_name='color primario',
        help_text='Color de la barra de navegación y botones principales (hex, ej: #1a1a2e).',
    )
    color_acento = models.CharField(
        max_length=7,
        default='#2e6da4',
        verbose_name='color de acento',
        help_text='Color de la barra de rol docente y links en la nav (hex, ej: #2e6da4).',
    )
    idioma_predeterminado = models.CharField(
        max_length=2,
        choices=IDIOMA_CHOICES,
        default='es',
        verbose_name='idioma predeterminado',
        help_text=(
            'Idioma que verá quien todavía no haya elegido uno. Cada persona '
            'puede cambiarlo luego desde el selector del sitio.'
        ),
    )
    contacto_privacidad = models.EmailField(
        blank=True,
        default='',
        verbose_name='correo de privacidad',
        help_text=(
            'Contacto responsable para ejercer derechos sobre datos personales. '
            'Si queda vacío, los consentimientos remiten al equipo docente local.'
        ),
    )
    instalacion_completada = models.BooleanField(
        default=False,
        verbose_name='instalación inicial completada',
        help_text='Se activa al finalizar el asistente inicial y evita que vuelva a abrirse.',
    )
    favicon_data = models.TextField(
        null=True,
        blank=True,
        verbose_name='favicon (datos, base64)',
    )
    favicon_content_type = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='favicon content-type',
    )
    error_consenso_min = models.PositiveSmallIntegerField(
        default=2,
        verbose_name='umbral de errores compartidos',
        help_text=(
            'Mínimo de estudiantes distintos que deben compartir la misma '
            'respuesta incorrecta para que aparezca en el panel "Errores compartidos". '
            'Valor recomendado: 2.'
        ),
    )
    umbral_min_intentos = models.PositiveSmallIntegerField(
        default=3,
        verbose_name='mínimo de intentos para ejercicio difícil',
        help_text=(
            'Un ejercicio aparece en el panel "Ejercicios difíciles" solo si '
            'acumuló al menos este número de intentos totales (evita ruido con '
            'ejercicios poco intentados). Valor recomendado: 3.'
        ),
    )
    umbral_riesgo = models.PositiveSmallIntegerField(
        default=5,
        verbose_name='umbral de racha de fallos (alerta de acompañamiento)',
        help_text=(
            'Cantidad de intentos incorrectos consecutivos en un mismo ejercicio '
            'a partir de la cual un estudiante aparece en el panel de alertas de '
            'acompañamiento. Valor recomendado: 5.'
        ),
    )
    umbral_silencio_dias = models.PositiveSmallIntegerField(
        default=7,
        verbose_name='días de silencio para alerta visual',
        help_text=(
            'Días sin actividad a partir de los cuales un estudiante recibe '
            'resaltado visual en el panel de seguimiento. Valor recomendado: 7.'
        ),
    )
    umbral_maraton = models.PositiveSmallIntegerField(
        default=6,
        verbose_name='umbral de concentración de práctica (ratio intentos/días)',
        help_text=(
            'Ratio intentos/días de actividad a partir del cual se considera '
            'que el estudiante concentró la práctica en muy pocos días. '
            'Valor recomendado: 6.'
        ),
    )
    umbral_arranque_dias = models.PositiveSmallIntegerField(
        default=14,
        verbose_name='ventana de arranque temprano (días)',
        help_text=(
            'Cantidad de días desde la apertura de una práctica durante los '
            'cuales se espera que el estudiante haya iniciado. Quienes no '
            'realizaron ningún intento en ese período aparecen en el panel '
            'de arranque tardío. Valor recomendado: 14.'
        ),
    )
    umbral_convergencia_min_estudiantes = models.PositiveSmallIntegerField(
        default=5,
        verbose_name='mínimo de estudiantes para curva de convergencia',
        help_text=(
            'Mínimo de estudiantes que deben haber intentado un ejercicio para '
            'mostrar su curva de convergencia en el detalle de ejercicio. '
            'Valor recomendado: 5.'
        ),
    )
    umbral_adivinacion_intentos = models.PositiveSmallIntegerField(
        default=5,
        verbose_name='mínimo de intentos para señal de baja variación',
        help_text=(
            'Cantidad mínima de intentos en el mismo ejercicio para activar '
            'la señal de "práctica con baja variación entre intentos". '
            'Valor recomendado: 5.'
        ),
    )
    umbral_adivinacion_segundos = models.PositiveSmallIntegerField(
        default=30,
        verbose_name='intervalo máximo (segundos) para señal de baja variación',
        help_text=(
            'Intervalo promedio entre intentos (en segundos) por debajo del '
            'cual se activa la señal de "práctica con baja variación entre '
            'intentos". Valor recomendado: 30.'
        ),
    )
    pistas_ia_activas = models.BooleanField(
        default=True,
        verbose_name='pistas pedagógicas con IA activas',
        help_text=(
            'Si está desactivado, no se generan pistas automáticas con Gemini/Groq '
            'al resolver ejercicios. Útil para controlar el consumo de tokens.'
        ),
    )
    revision_diccionario_activa = models.BooleanField(
        default=True,
        verbose_name='revisión de diccionarios con IA activa',
        help_text=(
            'Si está desactivado, no se envía el diccionario estudiantil a Groq '
            'para su revisión automática. Útil para controlar el consumo de tokens.'
        ),
    )

    class Meta:
        verbose_name = 'configuración del sitio'
        verbose_name_plural = 'configuración del sitio'

    def __str__(self):
        return self.nombre_sitio

    def save(self, *args, **kwargs):
        # Singleton: siempre sobrescribir la fila con pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def tiene_favicon(self):
        return bool(self.favicon_data)

    @classmethod
    def get(cls):
        """Devuelve la instancia única, creándola con defaults si no existe."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Usuario(AbstractUser):
    """Modelo de usuario de la plataforma.

    Extiende AbstractUser con el campo ``es_docente`` para distinguir
    docentes de estudiantes. Los admin usan ``is_staff=True`` (Django).

    Attributes:
        es_docente (bool): True si el usuario es docente. False por
            defecto (estudiante).

    Note:
        Referenciar siempre como ``settings.AUTH_USER_MODEL`` o con
        ``get_user_model()``, nunca importar directamente en código
        que se ejecuta antes de la inicialización de apps de Django.
    """

    es_docente = models.BooleanField(
        default=False,
        verbose_name='es docente',
        help_text=(
            'Designa que este usuario es docente. '
            'Los administradores usan is_staff=True.'
        ),
    )

    debe_cambiar_password = models.BooleanField(
        default=False,
        verbose_name='debe cambiar contraseña',
        help_text=(
            'Si True, el usuario será redirigido a cambiar su contraseña '
            'en el próximo login. Se activa al crear la cuenta y se limpia '
            'cuando el usuario guarda una nueva contraseña.'
        ),
    )

    consentimiento_pedagogico = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name='consentimiento pedagógico',
        help_text=(
            'El usuario acepta que sus datos, con información identificable, '
            'sean utilizados por sus docentes con fines pedagógicos. '
            'None = aún no respondió; True = aceptó; False = no aceptó.'
        ),
    )

    consentimiento_investigacion = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name='consentimiento de investigación',
        help_text=(
            'El usuario acepta que sus datos, debidamente anonimizados, '
            'sean utilizados con fines académicos y de investigación. '
            'None = aún no respondió; True = aceptó; False = no aceptó.'
        ),
    )

    consentimiento_contacto_seguimiento = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name='consentimiento contacto de seguimiento',
        help_text=(
            'El usuario acepta ser contactado por correo o WhatsApp para una '
            'encuesta de seguimiento voluntaria. '
            'None = aún no respondió; True = aceptó; False = no aceptó.'
        ),
    )

    fecha_consentimiento = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='fecha de consentimiento',
        help_text='Fecha y hora en que el usuario respondió los consentimientos.',
    )

    encuesta_completada = models.BooleanField(
        default=False,
        verbose_name='encuesta de onboarding completada',
        help_text=(
            'True cuando el estudiante completó (o se salteó por consentimiento negativo) '
            'la encuesta socioeducativa de onboarding.'
        ),
    )

    research_id = models.UUIDField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        unique=True,
        verbose_name='ID de investigación',
        help_text=(
            'Pseudónimo estable para exportación de datos de investigación. '
            'Se genera al confirmar consentimiento_investigacion=True y se '
            'anula si el estudiante revoca el consentimiento. '
            'Nunca se expone en la UI. Permite cruzar datasets '
            '(encuesta ↔ intentos) sin revelar la identidad del estudiante.'
        ),
    )

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    @property
    def nombre_display(self) -> str:
        """Nombre completo si está cargado, username como fallback."""
        nombre_completo = self.get_full_name()
        return nombre_completo if nombre_completo else self.username

    def __str__(self) -> str:
        if self.is_staff:
            rol = 'admin'
        elif self.es_docente:
            rol = 'docente'
        else:
            rol = 'estudiante'
        return f'{self.username} ({rol})'


# ─── Choices para EncuestaEstudiante ───────────────────────────────────────

FACULTAD_CHOICES = [
    ('agronomia', 'Agronomía'),
    ('arquitectura', 'Arquitectura, Diseño y Urbanismo'),
    ('economicas', 'Ciencias Económicas'),
    ('exactas', 'Ciencias Exactas y Naturales'),
    ('medicas', 'Ciencias Médicas'),
    ('sociales', 'Ciencias Sociales'),
    ('veterinarias', 'Ciencias Veterinarias'),
    ('derecho', 'Derecho'),
    ('farmacia', 'Farmacia y Bioquímica'),
    ('filosofia', 'Filosofía y Letras'),
    ('ingenieria', 'Ingeniería'),
    ('odontologia', 'Odontología'),
    ('psicologia', 'Psicología'),
]

CARRERA_CHOICES = [
    ('abogacia', 'Abogacía'),
    ('actuario', 'Actuario'),
    ('administracion', 'Administración'),
    ('arquitectura', 'Arquitectura'),
    ('artes', 'Artes'),
    ('bibliotecologia', 'Bibliotecología y Ciencia de la Información'),
    ('bioquimica', 'Bioquímica'),
    ('bioterios', 'Bioterios'),
    ('caligrafo_publico', 'Calígrafo Público'),
    ('ciencia_politica', 'Ciencia Política'),
    ('ciencia_tec_alimentos', 'Ciencia y Tecnología de Alimentos'),
    ('ciencias_ambientales', 'Ciencias Ambientales'),
    ('ciencias_antropologicas', 'Ciencias Antropológicas'),
    ('ciencias_biologicas', 'Ciencias Biológicas'),
    ('ciencias_atmosfera', 'Ciencias de la Atmósfera'),
    ('ciencias_computacion', 'Ciencias de la Computación'),
    ('ciencias_comunicacion', 'Ciencias de la Comunicación'),
    ('ciencias_datos', 'Ciencias de Datos'),
    ('ciencias_educacion', 'Ciencias de la Educación'),
    ('ciencias_fisicas', 'Ciencias Físicas'),
    ('ciencias_geologicas', 'Ciencias Geológicas'),
    ('ciencias_matematicas', 'Ciencias Matemáticas'),
    ('ciencias_quimicas', 'Ciencias Químicas'),
    ('ciencias_veterinarias', 'Ciencias Veterinarias'),
    ('construcciones_navales', 'Construcciones Navales'),
    ('contador_publico', 'Contador Público'),
    ('cosmetologia', 'Cosmetología facial y corporal'),
    ('diseno_imagen_sonido', 'Diseño de Imagen y Sonido'),
    ('diseno_indumentaria', 'Diseño de Indumentaria'),
    ('diseno_grafico', 'Diseño Gráfico'),
    ('diseno_industrial', 'Diseño Industrial'),
    ('diseno_textil', 'Diseño Textil'),
    ('economia', 'Economía'),
    ('economia_agr', 'Economía y Administración Agraria'),
    ('edicion', 'Edición'),
    ('enfermeria', 'Enfermería'),
    ('farmacia', 'Farmacia'),
    ('filosofia', 'Filosofía'),
    ('floricultura', 'Floricultura'),
    ('fonoaudiologia', 'Fonoaudiología'),
    ('geografia', 'Geografía'),
    ('gestion_agroalimentos', 'Gestión de Agroalimentos'),
    ('hemoterapia', 'Hemoterapia e inmunohematología'),
    ('historia', 'Historia'),
    ('ingenieria_civil', 'Ingeniería Civil'),
    ('ingenieria_alimentos', 'Ingeniería de Alimentos'),
    ('ingenieria_electricista', 'Ingeniería Electricista'),
    ('ingenieria_electronica', 'Ingeniería Electrónica'),
    ('ingenieria_agrimensura', 'Ingeniería en Agrimensura'),
    ('ingenieria_informatica', 'Ingeniería en Informática'),
    ('ingenieria_petroleo', 'Ingeniería en Petróleo'),
    ('ingenieria_industrial', 'Ingeniería Industrial'),
    ('ingenieria_mecanica', 'Ingeniería Mecánica'),
    ('ingenieria_naval', 'Ingeniería Naval y Mecánica'),
    ('ingenieria_quimica', 'Ingeniería Química'),
    ('instrumentacion_qx', 'Instrumentación Quirúrgica'),
    ('jardineria', 'Jardinería'),
    ('kinesiologia', 'Kinesiología y Fisiatría'),
    ('letras', 'Letras'),
    ('martillero_rural', 'Martillero y Corredor Público Rural'),
    ('medicina', 'Medicina'),
    ('medicina_nuclear', 'Medicina Nuclear'),
    ('musicoterapia', 'Musicoterapia'),
    ('nutricion', 'Nutrición'),
    ('obstetricia', 'Obstetricia'),
    ('oceanografia', 'Oceanografía'),
    ('odontologia', 'Odontología'),
    ('optica', 'Óptica y Contactología'),
    ('paleontologia', 'Paleontología'),
    ('planif_paisaje', 'Planificación y Diseño del Paisaje'),
    ('podologia', 'Podología'),
    ('practicas_cardiologicas', 'Prácticas cardiológicas'),
    ('produccion_animal', 'Producción Animal'),
    ('radiologia', 'Producción de Bioimágenes (Radiología)'),
    ('prod_vegetal_organica', 'Producción Vegetal Orgánica'),
    ('psicologia', 'Psicología'),
    ('relaciones_trabajo', 'Relaciones del Trabajo'),
    ('sistemas_info_org', 'Sistemas de Información de las Organizaciones'),
    ('sociologia', 'Sociología'),
    ('terapia_ocupacional', 'Terapia Ocupacional'),
    ('trabajo_social', 'Trabajo Social'),
    ('traductorado_publico', 'Traductorado Público'),
    ('turismo_rural', 'Turismo Rural'),
    ('ingenieria_agronoma', 'Ingeniera/o Agrónoma/o'),
]

PROVINCIA_CHOICES = [
    ('buenos_aires', 'Buenos Aires (Interior)'),
    ('caba', 'Ciudad Autónoma de Buenos Aires'),
    ('catamarca', 'Catamarca'),
    ('chaco', 'Chaco'),
    ('chubut', 'Chubut'),
    ('cordoba', 'Córdoba'),
    ('corrientes', 'Corrientes'),
    ('entre_rios', 'Entre Ríos'),
    ('formosa', 'Formosa'),
    ('jujuy', 'Jujuy'),
    ('la_pampa', 'La Pampa'),
    ('la_rioja', 'La Rioja'),
    ('mendoza', 'Mendoza'),
    ('misiones', 'Misiones'),
    ('neuquen', 'Neuquén'),
    ('rio_negro', 'Río Negro'),
    ('salta', 'Salta'),
    ('san_juan', 'San Juan'),
    ('san_luis', 'San Luis'),
    ('santa_cruz', 'Santa Cruz'),
    ('santa_fe', 'Santa Fe'),
    ('santiago_del_estero', 'Santiago del Estero'),
    ('tierra_del_fuego', 'Tierra del Fuego'),
    ('tucuman', 'Tucumán'),
]


class EncuestaEstudiante(models.Model):
    """Datos socioeducativos del estudiante, recopilados en el onboarding.

    Solo existe si ``Usuario.consentimiento_pedagogico = True``.
    Los campos de encuesta completa solo se llenan si la comisión tiene
    ``tipo_encuesta='completa'``; de lo contrario, quedan en null.
    """

    # ── Datos básicos (Sección 1, presentes en ambos tipos) ──────────────
    estudiante = models.OneToOneField(
        'Usuario',
        on_delete=models.CASCADE,
        related_name='encuesta',
        verbose_name='estudiante',
    )
    dni = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='DNI',
    )
    whatsapp = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name='WhatsApp',
    )
    fecha_nacimiento = models.DateField(
        null=True,
        blank=True,
        verbose_name='fecha de nacimiento',
    )
    # ── Facultad y carrera (tipo completa) ───────────────────────────────
    facultad = models.CharField(
        max_length=30,
        choices=FACULTAD_CHOICES,
        blank=True,
        default='',
        verbose_name='facultad',
    )
    carrera = models.CharField(
        max_length=30,
        choices=CARRERA_CHOICES,
        blank=True,
        default='',
        verbose_name='carrera',
    )

    # ── Geografía / migración (tipo completa) ────────────────────────────
    origen_caba_gba = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='¿Es de CABA o GBA?',
    )
    vive_en = models.CharField(
        max_length=10,
        choices=[('caba', 'Dentro de CABA'), ('gba', 'Dentro de GBA')],
        blank=True,
        default='',
        verbose_name='vive en',
    )
    mudado_con_familia = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='se mudó con familia',
    )
    mudado_para_trabajar_estudiar = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='se mudó para trabajar/estudiar',
    )
    tiempo_mudado = models.CharField(
        max_length=15,
        choices=[
            ('menos_1', 'Menos de 1 año'),
            ('1_2', 'Entre 1 y 2 años'),
            ('2_5', 'Entre 2 y 5 años'),
            ('mas_5', 'Más de 5 años'),
        ],
        blank=True,
        default='',
        verbose_name='tiempo mudado/a',
    )
    desde_donde = models.CharField(
        max_length=20,
        choices=[('argentina', 'Desde otra provincia de Argentina'), ('fuera_argentina', 'Desde fuera de Argentina')],
        blank=True,
        default='',
        verbose_name='desde dónde se mudó',
    )
    provincia_origen = models.CharField(
        max_length=30,
        choices=PROVINCIA_CHOICES,
        blank=True,
        default='',
        verbose_name='provincia de origen',
    )
    pais_origen = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='país de origen',
    )

    # ── Situación personal (tipo completa) ───────────────────────────────
    necesita_adecuacion = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='necesita adecuación',
    )
    tiene_cud = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='tiene CUD',
    )
    con_quien_vive = models.CharField(
        max_length=25,
        choices=[
            ('familia_nuclear', 'Con mi familia (padres/hermanos)'),
            ('pareja', 'Con mi pareja/hijos'),
            ('otros_familiares', 'Con otros familiares'),
            ('amigos', 'Con amigos/compañeros'),
            ('solo', 'Solo/a'),
            ('residencia', 'En residencia u hogar universitario'),
        ],
        blank=True,
        default='',
        verbose_name='con quién vive',
    )
    tiempo_viaje_puan = models.CharField(
        max_length=15,
        choices=[
            ('menos_30', 'Menos de 30 min'),
            ('30_60', 'Entre 30 y 60 min'),
            ('60_90', 'Entre 60 y 90 min'),
            ('mas_90', 'Más de 90 min'),
        ],
        blank=True,
        default='',
        verbose_name='tiempo de viaje a Puán',
    )
    situacion_laboral = models.CharField(
        max_length=15,
        choices=[
            ('no_trabajo', 'No trabajo y no estoy buscando'),
            ('busco', 'Busco trabajo'),
            ('hasta_4', 'Trabajo hasta 4 horas por día'),
            ('4_6', 'Trabajo entre 4 y 6 horas por día'),
            ('mas_6', 'Trabajo 6 o más horas por día'),
        ],
        blank=True,
        default='',
        verbose_name='situación laboral',
    )
    dias_trabaja = models.CharField(
        max_length=10,
        choices=[
            ('no', 'No trabajo'),
            ('menos_5', 'Trabajo menos de 5 días a la semana'),
            ('5', 'Trabajo 5 días de la semana'),
            ('mas_5', 'Trabajo más de 5 días a la semana'),
        ],
        blank=True,
        default='',
        verbose_name='días que trabaja',
    )
    acceso_internet = models.JSONField(
        null=True,
        blank=True,
        verbose_name='acceso a internet',
        help_text='Lista de modalidades de acceso, ej: ["wifi_hogar", "datos_abono"]',
    )
    dispositivos = models.JSONField(
        null=True,
        blank=True,
        verbose_name='dispositivos',
        help_text='Dict por dispositivo: {"celular": "individual", "laptop": "no_tengo"}',
    )

    # ── Secundaria (tipo completa) ────────────────────────────────────────
    tiempo_desde_secundaria = models.CharField(
        max_length=15,
        choices=[
            ('menos_1', 'Menos de un año'),
            ('1_3', 'Entre 1 y 3 años'),
            ('mas_3', 'Más de 3 años'),
        ],
        blank=True,
        default='',
        verbose_name='tiempo desde secundaria',
    )
    tipo_escuela = models.CharField(
        max_length=20,
        choices=[
            ('bachillerato', 'Bachillerato'),
            ('comercial', 'Comercial'),
            ('tecnico', 'Técnico Profesional'),
            ('artistica', 'Artística'),
            ('especial', 'Especial'),
            ('rural', 'Rural'),
            ('ja', 'de Jóvenes y Adultos'),
            ('intercultural', 'Intercultural Bilingüe'),
            ('domiciliaria', 'Domiciliaria/Hospitalaria'),
            ('encierro', 'en Contexto de Encierro'),
        ],
        blank=True,
        default='',
        verbose_name='tipo de escuela secundaria',
    )

    # ── Estudios superiores (tipo completa) ──────────────────────────────
    estudios_superiores = models.CharField(
        max_length=15,
        choices=[
            ('no', 'No, esta es mi primera carrera de nivel superior'),
            ('si_uba', 'Sí, estudié o estoy estudiando en la UBA'),
            ('si_fuera_uba', 'Sí, en otra institución'),
        ],
        blank=True,
        default='',
        verbose_name='estudios superiores previos',
    )
    carrera_uba_anterior = models.CharField(
        max_length=30,
        choices=CARRERA_CHOICES,
        blank=True,
        default='',
        verbose_name='carrera UBA anterior',
    )
    termino_cbc_anterior = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='terminó CBC anterior',
    )
    se_recibio_uba = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='se recibió en UBA',
    )
    tipo_inst_fuera_uba = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='tipo de institución (fuera de UBA)',
    )
    carrera_fuera_uba = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='carrera fuera de UBA',
    )
    se_recibio_fuera_uba = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='se recibió fuera de UBA',
    )

    # ── CBC (tipo completa) ───────────────────────────────────────────────
    hizo_uba_xxi = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='hizo UBA XXI',
    )
    tiempo_en_cbc = models.CharField(
        max_length=15,
        choices=[
            ('primero', 'Es mi primer cuatrimestre'),
            ('segundo', 'Es mi segundo cuatrimestre'),
            ('1_2_anios', 'Entre 1 y 2 años'),
            ('mas_2_anios', 'Más de 2 años'),
        ],
        blank=True,
        default='',
        verbose_name='tiempo en el CBC',
    )
    interrupcion_cbc = models.CharField(
        max_length=15,
        choices=[
            ('no', 'No, nunca interrumpí'),
            ('un_cuatr', 'Sí, un cuatrimestre'),
            ('mas', 'Sí, más de un cuatrimestre'),
        ],
        blank=True,
        default='',
        verbose_name='interrupción en el CBC',
    )
    ya_curso_ipc = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='ya cursó IPC',
    )
    motivo_no_termino_ipc = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='motivo por el que no terminó IPC',
    )
    materias_aprobadas = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name='materias aprobadas en el CBC',
    )

    # ── Lógica y polémica (tipo completa) ────────────────────────────────
    acertijo_silogismo = models.CharField(
        max_length=10,
        choices=[
            ('mas_alto', 'Más alto'),
            ('mas_bajo', 'Más bajo'),
        ],
        blank=True,
        default='',
        verbose_name='acertijo: silogismo',
    )
    acertijo_cirugia = models.TextField(
        blank=True,
        default='',
        verbose_name='acertijo: cirugía',
    )
    acertijo_cirugia_correcto = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='acertijo cirugía: correcto (evaluado por IA)',
    )
    acertijo_hilera = models.CharField(
        max_length=10,
        choices=[
            ('rodriguez', 'Rodríguez'),
            ('rivera', 'Rivera'),
            ('posada', 'Posada'),
        ],
        blank=True,
        default='',
        verbose_name='acertijo: hilera',
    )
    articulo_risa = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='creyó el artículo de la risa',
    )
    que_es_ciencia = models.TextField(
        blank=True,
        default='',
        verbose_name='¿qué es la ciencia? (texto libre)',
    )

    class Meta:
        verbose_name = 'encuesta de estudiante'
        verbose_name_plural = 'encuestas de estudiantes'

    def __str__(self) -> str:
        return f'Encuesta de {self.estudiante.username}'
