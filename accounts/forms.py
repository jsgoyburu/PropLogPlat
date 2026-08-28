import re
import secrets
from datetime import date
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.core.management.utils import get_random_secret_key
from django.utils.translation import gettext

from accounts.facultades import get_carreras_unificadas_por_clave
from accounts.models import (
    CARRERA_CHOICES,
    FACULTAD_CHOICES,
    PROVINCIA_CHOICES,
)

User = get_user_model()


BOOLEAN_CHOICES = (('True', 'Sí'), ('False', 'No'))


def _installer_text(key):
    """Traduce una clave del instalador exclusivamente desde ``django.mo``."""

    return gettext(f'installer.{key}')


def _localize_fields(form, namespace, translated_labels, translated_help):
    for name in translated_labels:
        form.fields[name].label = _installer_text(f'{namespace}.{name}.label')
    for name in translated_help:
        form.fields[name].help_text = _installer_text(f'{namespace}.{name}.help')


class ConfiguracionEntornoForm(forms.Form):
    """Prepara variables para cualquier proveedor sin persistir secretos."""

    deployment_kind = forms.ChoiceField(
        label='¿Dónde está instalado?',
        choices=(
            ('managed', 'Proveedor administrado (Railway, Render, Fly.io, Heroku…)'),
            ('container', 'Contenedor Docker propio'),
            ('self_hosted', 'Servidor propio o VPS'),
            ('local', 'Mi computadora, para probar'),
        ),
        initial='managed',
        help_text='Cambia las instrucciones; el archivo generado es el mismo.',
    )
    authorization_token = forms.CharField(
        label='SETUP_TOKEN actual (solo para escribir en el servidor)',
        required=False,
        strip=True,
        widget=forms.PasswordInput(attrs={'autocomplete': 'off'}),
        help_text='No hace falta para previsualizar o descargar. Nunca se guarda en la base.',
    )
    secret_key = forms.CharField(
        label='SECRET_KEY', min_length=40, max_length=200,
        initial=get_random_secret_key,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'new-password'}),
        help_text='Clave aleatoria de Django. Guardala y no la cambies después de empezar a usar el sitio.',
    )
    setup_token = forms.CharField(
        label='SETUP_TOKEN nueva', min_length=16, max_length=200,
        initial=lambda: secrets.token_urlsafe(32),
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'new-password'}),
        help_text='Clave temporal para volver a este asistente después del reinicio.',
    )
    debug = forms.ChoiceField(
        label='DEBUG', choices=BOOLEAN_CHOICES, initial='False',
        help_text='Elegí No/False si el sitio puede verse desde internet.',
    )
    allowed_hosts = forms.CharField(
        label='ALLOWED_HOSTS', max_length=1000,
        help_text='Dominios separados por coma, sin https:// ni barras. Ej.: logica.example.org',
    )
    csrf_trusted_origins = forms.CharField(
        label='CSRF_TRUSTED_ORIGINS', required=False, max_length=2000,
        help_text='URLs HTTPS completas separadas por coma. Normalmente coincide con los dominios anteriores.',
    )
    database_url = forms.CharField(
        label='DATABASE_URL', required=False, max_length=3000,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'off'}),
        help_text='URL completa de PostgreSQL. Si el proveedor ya la inyecta, dejala vacía para no copiar el secreto.',
    )
    use_database_url = forms.ChoiceField(
        label='USE_DATABASE_URL', choices=BOOLEAN_CHOICES, initial='True',
        help_text='Sí hace que una instalación local también use PostgreSQL cuando DATABASE_URL existe.',
    )
    redis_url = forms.CharField(
        label='REDIS_URL', required=False, max_length=3000,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'off'}),
        help_text='Opcional. Recomendado si habrá más de un proceso o réplica.',
    )
    email_provider = forms.ChoiceField(
        label='Envío de correo',
        choices=(
            ('none', 'Todavía no configurar correo'),
            ('brevo', 'Brevo mediante API HTTP (recomendado)'),
            ('smtp', 'Servidor SMTP'),
        ),
        initial='none',
    )
    brevo_api_key = forms.CharField(
        label='BREVO_API_KEY', required=False, max_length=500,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'off'}),
        help_text='Se obtiene en Brevo → SMTP & API → API Keys.',
    )
    email_host = forms.CharField(label='EMAIL_HOST', required=False, max_length=255)
    email_port = forms.IntegerField(label='EMAIL_PORT', required=False, initial=587, min_value=1, max_value=65535)
    email_host_user = forms.CharField(
        label='EMAIL_HOST_USER', required=False, max_length=500,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'off'}),
    )
    email_host_password = forms.CharField(
        label='EMAIL_HOST_PASSWORD', required=False, max_length=1000,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'off'}),
    )
    email_use_tls = forms.ChoiceField(label='EMAIL_USE_TLS', choices=BOOLEAN_CHOICES, initial='True')
    email_use_ssl = forms.ChoiceField(label='EMAIL_USE_SSL', choices=BOOLEAN_CHOICES, initial='False')
    default_from_email = forms.CharField(
        label='DEFAULT_FROM_EMAIL', required=False, max_length=500,
        help_text='Ej.: PropLogPlat <no-reply@tu-dominio.org>. El dominio debe estar autenticado.',
    )
    trusted_proxy_count = forms.IntegerField(
        label='TRUSTED_PROXY_COUNT', initial=1, min_value=0, max_value=10,
        help_text='Dejá 1 con un proveedor común. Cambialo solo si sabés cuántos proxies hay delante.',
    )
    gemini_api_key = forms.CharField(
        label='GEMINI_API_KEY', required=False, max_length=1000,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'off'}),
        help_text='Opcional: proveedor principal de pistas pedagógicas.',
    )
    groq_api_key = forms.CharField(
        label='GROQ_API_KEY', required=False, max_length=1000,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'off'}),
        help_text='Opcional: fallback de pistas y revisión de diccionarios.',
    )
    mcp_transport = forms.ChoiceField(
        label='MCP_TRANSPORT', required=False,
        choices=(('', 'No publicar MCP desde este proceso'), ('stdio', 'stdio'), ('http', 'HTTP')),
    )
    mcp_issuer_url = forms.URLField(
        label='MCP_ISSUER_URL', required=False, max_length=2000,
        help_text='Solo para MCP por HTTP con autenticación OAuth.',
    )
    port = forms.IntegerField(
        label='PORT', initial=8000, min_value=1, max_value=65535,
        help_text='El proveedor suele inyectarlo automáticamente; 8000 es el valor local.',
    )
    admin_username = forms.CharField(
        label='ADMIN_USERNAME', required=False, max_length=150,
        help_text='Dejá los tres ADMIN_* vacíos si vas a terminar con este asistente.',
    )
    admin_email = forms.EmailField(label='ADMIN_EMAIL', required=False)
    admin_password = forms.CharField(
        label='ADMIN_PASSWORD', required=False, max_length=1000,
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'off'}),
    )
    write_to_server = forms.BooleanField(
        label='Guardar también como .env en este servidor', required=False,
        help_text=(
            'Solo para computadora propia/VPS/volumen persistente. En Railway, Render y similares '
            'usá el panel del proveedor: el disco puede borrarse en cada despliegue.'
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _localize_fields(
            self,
            'env',
            translated_labels={
                'deployment_kind', 'authorization_token', 'setup_token',
                'email_provider', 'write_to_server',
            },
            translated_help={
                name for name, field in self.fields.items() if field.help_text
            },
        )
        yes_no = (('True', _installer_text('choice.yes')), ('False', _installer_text('choice.no')))
        for name in ('debug', 'use_database_url', 'email_use_tls', 'email_use_ssl'):
            self.fields[name].choices = yes_no
        self.fields['deployment_kind'].choices = (
            ('managed', _installer_text('choice.managed')),
            ('container', _installer_text('choice.container')),
            ('self_hosted', _installer_text('choice.self_hosted')),
            ('local', _installer_text('choice.local')),
        )
        self.fields['email_provider'].choices = (
            ('none', _installer_text('choice.email_none')),
            ('brevo', _installer_text('choice.email_brevo')),
            ('smtp', _installer_text('choice.email_smtp')),
        )
        self.fields['mcp_transport'].choices = (
            ('', _installer_text('choice.mcp_none')),
            ('stdio', 'stdio'),
            ('http', 'HTTP'),
        )

    def clean_allowed_hosts(self):
        raw = self.cleaned_data['allowed_hosts']
        hosts = [host.strip() for host in raw.split(',') if host.strip()]
        if not hosts:
            raise forms.ValidationError(_installer_text('error.host_required'))
        for host in hosts:
            if '://' in host or '/' in host or any(char.isspace() for char in host):
                raise forms.ValidationError(_installer_text('error.host_invalid') % {'value': host})
        return ','.join(dict.fromkeys(hosts))

    def clean_csrf_trusted_origins(self):
        raw = self.cleaned_data.get('csrf_trusted_origins', '')
        origins = [origin.strip().rstrip('/') for origin in raw.split(',') if origin.strip()]
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path:
                raise forms.ValidationError(_installer_text('error.origin_invalid') % {'value': origin})
        return ','.join(dict.fromkeys(origins))

    def clean_database_url(self):
        value = self.cleaned_data.get('database_url', '').strip()
        if value and urlsplit(value).scheme not in ('postgres', 'postgresql'):
            raise forms.ValidationError(_installer_text('error.database_invalid'))
        return value

    def clean(self):
        cleaned = super().clean()

        for name, value in cleaned.items():
            if isinstance(value, str) and ('\n' in value or '\r' in value):
                self.add_error(name, _installer_text('error.no_newlines'))

        secret_key = cleaned.get('secret_key', '')
        if secret_key.startswith('cambiar-') or len(set(secret_key)) < 10:
            self.add_error('secret_key', _installer_text('error.secret_weak'))

        if cleaned.get('debug') == 'False' and not cleaned.get('database_url'):
            # Puede estar inyectada por el proveedor; solo se informa en la UI.
            pass

        provider = cleaned.get('email_provider')
        if provider == 'brevo' and not cleaned.get('brevo_api_key'):
            self.add_error('brevo_api_key', _installer_text('error.brevo_required'))
        if provider == 'smtp':
            for name in ('email_host', 'email_port', 'email_host_user', 'email_host_password'):
                if not cleaned.get(name):
                    self.add_error(name, _installer_text('error.smtp_required'))
            if cleaned.get('email_use_tls') == 'True' and cleaned.get('email_use_ssl') == 'True':
                self.add_error('email_use_ssl', _installer_text('error.tls_ssl_exclusive'))

        if cleaned.get('mcp_transport') == 'http' and not cleaned.get('mcp_issuer_url'):
            self.add_error('mcp_issuer_url', _installer_text('error.mcp_issuer_required'))

        admin_values = [
            cleaned.get('admin_username'), cleaned.get('admin_email'), cleaned.get('admin_password'),
        ]
        if any(admin_values) and not all(admin_values):
            for name in ('admin_username', 'admin_email', 'admin_password'):
                if not cleaned.get(name):
                    self.add_error(name, _installer_text('error.admin_all_or_none'))

        if cleaned.get('write_to_server'):
            received = cleaned.get('authorization_token', '')
            expected = settings.SETUP_TOKEN
            if not (settings.DEBUG and not expected):
                if not expected or not secrets.compare_digest(received, expected):
                    self.add_error('authorization_token', _installer_text('error.authorization_invalid'))
        return cleaned


class InstalacionInicialForm(forms.Form):
    """Crea la identidad, criterios iniciales, cohorte y primer administrador."""

    token = forms.CharField(
        label='Clave de instalación',
        required=False,
        strip=True,
        widget=forms.PasswordInput(attrs={'autocomplete': 'off'}),
        help_text='Es la clave SETUP_TOKEN definida al desplegar el sitio.',
    )
    nombre_sitio = forms.CharField(
        label='Nombre del sitio',
        max_length=100,
        initial='PropLogPlat',
    )
    idioma_predeterminado = forms.ChoiceField(
        label='Idioma predeterminado',
        choices=(
            ('es', 'Castellano'),
            ('en', 'English'),
            ('fr', 'Français'),
            ('de', 'Deutsch'),
            ('zh-hans', '简体中文'),
        ),
        initial='es',
    )
    contacto_privacidad = forms.EmailField(
        label='Correo responsable de privacidad',
        required=False,
        help_text=(
            'Se mostrará en los consentimientos para consultas o pedidos sobre datos. '
            'Puede completarse luego desde el admin.'
        ),
    )
    color_primario = forms.CharField(
        label='Color principal', required=False, initial='#1a1a2e', max_length=7,
        help_text='Formato hexadecimal, por ejemplo #1a1a2e.',
    )
    color_acento = forms.CharField(
        label='Color de acento', required=False, initial='#2e6da4', max_length=7,
        help_text='Formato hexadecimal, por ejemplo #2e6da4.',
    )
    favicon_upload = forms.FileField(
        label='Ícono del sitio (opcional)', required=False,
        help_text='Archivo .ico, .png o .svg de hasta 512 KB.',
    )
    cohorte_anio = forms.IntegerField(
        label='Año de la primera cohorte', required=False, initial=date.today().year,
        min_value=2000, max_value=2200,
        help_text='La cohorte es la camada de pertenencia del estudiantado.',
    )
    cohorte_cuatrimestre = forms.TypedChoiceField(
        label='Cuatrimestre de la primera cohorte', required=False, coerce=int,
        choices=((1, '1º'), (2, '2º')), initial=1 if date.today().month <= 7 else 2,
    )
    error_consenso_min = forms.IntegerField(
        label='Estudiantes mínimos para mostrar un error compartido', required=False,
        initial=2, min_value=2, max_value=100,
    )
    umbral_min_intentos = forms.IntegerField(
        label='Intentos mínimos para considerar difícil un ejercicio', required=False,
        initial=3, min_value=1, max_value=100,
    )
    umbral_riesgo = forms.IntegerField(
        label='Intentos incorrectos consecutivos para alerta de acompañamiento', required=False,
        initial=5, min_value=1, max_value=100,
    )
    umbral_silencio_dias = forms.IntegerField(
        label='Días sin actividad para alerta visual', required=False,
        initial=7, min_value=1, max_value=365,
    )
    umbral_maraton = forms.IntegerField(
        label='Ratio de concentración de práctica', required=False,
        initial=6, min_value=1, max_value=100,
    )
    umbral_arranque_dias = forms.IntegerField(
        label='Ventana de arranque temprano (días)', required=False,
        initial=14, min_value=1, max_value=365,
    )
    umbral_convergencia_min_estudiantes = forms.IntegerField(
        label='Estudiantes mínimos para curva de convergencia', required=False,
        initial=5, min_value=1, max_value=1000,
    )
    umbral_adivinacion_intentos = forms.IntegerField(
        label='Intentos mínimos para señal de baja variación', required=False,
        initial=5, min_value=2, max_value=100,
    )
    umbral_adivinacion_segundos = forms.IntegerField(
        label='Intervalo máximo para señal de baja variación (segundos)', required=False,
        initial=30, min_value=1, max_value=3600,
    )
    pistas_ia_activas = forms.ChoiceField(
        label='Activar pistas pedagógicas con IA', required=False,
        choices=BOOLEAN_CHOICES, initial='True',
        help_text='Desactivalas si no configuraste Gemini/Groq o no querés enviar esos datos.',
    )
    revision_diccionario_activa = forms.ChoiceField(
        label='Activar revisión de diccionarios con IA', required=False,
        choices=BOOLEAN_CHOICES, initial='True',
        help_text='Desactivalo si no configuraste Groq o no querés usar ese servicio.',
    )
    username = forms.CharField(label='Usuario administrador', max_length=150)
    email = forms.EmailField(label='Correo electrónico')
    password1 = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label='Repetir contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _localize_fields(
            self,
            'site',
            translated_labels=set(self.fields),
            translated_help={
                name for name, field in self.fields.items()
                if field.help_text and name != 'password1'
            },
        )
        self.fields['password1'].help_text = password_validation.password_validators_help_text_html()
        yes_no = (('True', _installer_text('choice.yes')), ('False', _installer_text('choice.no')))
        self.fields['pistas_ia_activas'].choices = yes_no
        self.fields['revision_diccionario_activa'].choices = yes_no

    def clean_token(self):
        recibido = self.cleaned_data.get('token', '')
        esperado = settings.SETUP_TOKEN
        if settings.DEBUG and not esperado:
            return recibido
        if not esperado or not secrets.compare_digest(recibido, esperado):
            raise forms.ValidationError(_installer_text('error.setup_token_invalid'))
        return recibido

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_installer_text('error.username_exists'))
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_installer_text('error.email_exists'))
        return email

    def clean_favicon_upload(self):
        archivo = self.cleaned_data.get('favicon_upload')
        if not archivo:
            return archivo
        if archivo.size > 512 * 1024:
            raise forms.ValidationError(_installer_text('error.favicon_too_large'))
        nombre = archivo.name.lower()
        permitidos = ('.ico', '.png', '.svg')
        if not nombre.endswith(permitidos):
            raise forms.ValidationError(_installer_text('error.favicon_type'))
        return archivo

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', _installer_text('error.password_mismatch'))
        if password1:
            provisional = User(
                username=cleaned_data.get('username', ''),
                email=cleaned_data.get('email', ''),
            )
            try:
                password_validation.validate_password(password1, user=provisional)
            except forms.ValidationError as error:
                self.add_error('password1', error)

        patron_color = re.compile(r'^#[0-9a-fA-F]{6}$')
        for name in ('color_primario', 'color_acento'):
            value = cleaned_data.get(name) or self.fields[name].initial
            if not patron_color.fullmatch(value):
                self.add_error(name, _installer_text('error.color_format'))
        return cleaned_data

_CONSENT_CHOICES = [
    ('true', 'Sí, presto mi consentimiento'),
    ('false', 'No, no presto mi consentimiento'),
]

_INTERNET_CHOICES = [
    ('no_tengo', 'No tengo acceso a internet'),
    ('datos_prepaga', 'Datos en plan prepago'),
    ('datos_abono', 'Datos con abono mensual'),
    ('wifi_hogar', 'WiFi'),
    ('cable', 'Conexión cableada'),
]

_DISPOSITIVO_CHOICES = [
    ('individual', 'Sí, tengo uno propio'),
    ('compartido', 'Sí, lo comparto'),
    ('no_tengo', 'No tengo'),
]


class PerfilForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Email',
        }


class RegistroEstudianteComisionForm(forms.ModelForm):
    """Formulario de auto-registro de estudiante desde link de comisión."""

    password1 = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput,
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label='Repetir contraseña',
        strip=False,
        widget=forms.PasswordInput,
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        labels = {
            'username': 'Usuario',
            'email': 'Correo electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
        }

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if not email:
            raise forms.ValidationError('Este campo es obligatorio.')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con este email.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
            return cleaned_data

        if password1:
            user = self.instance if self.instance and self.instance.pk else User(
                username=cleaned_data.get('username', ''),
                email=cleaned_data.get('email', ''),
                first_name=cleaned_data.get('first_name', ''),
                last_name=cleaned_data.get('last_name', ''),
            )
            try:
                password_validation.validate_password(password1, user=user)
            except forms.ValidationError as error:
                self.add_error('password1', error)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.es_docente = False
        user.is_staff = False
        # En auto-registro ya define contraseña: onboarding continúa por consentimientos/encuesta.
        user.debe_cambiar_password = False
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class ConsentimientosForm(forms.Form):
    """Formulario de consentimientos informados.

    Requiere una respuesta activa (no wrapped consent): el usuario debe
    seleccionar explícitamente "Sí" o "No" en cada ítem.
    Solo ``consentimiento_pedagogico`` es siempre requerido.
    Los campos Q9/Q10 son opcionales: si tipo='basica' no se renderizan
    y su ausencia se interpreta como False en la vista.
    """

    consentimiento_pedagogico = forms.ChoiceField(
        choices=_CONSENT_CHOICES,
        widget=forms.RadioSelect,
        required=True,
        label='Consentimiento pedagógico',
        error_messages={'required': 'Debés seleccionar una opción para este consentimiento.'},
    )

    consentimiento_investigacion = forms.ChoiceField(
        choices=_CONSENT_CHOICES,
        widget=forms.RadioSelect,
        required=False,
        label='Consentimiento de investigación',
        error_messages={'required': 'Debés seleccionar una opción para este consentimiento.'},
    )

    consentimiento_contacto_seguimiento = forms.ChoiceField(
        choices=_CONSENT_CHOICES,
        widget=forms.RadioSelect,
        required=False,
        label='Consentimiento de contacto para seguimiento',
        error_messages={'required': 'Debés seleccionar una opción para este consentimiento.'},
    )

    def clean(self):
        cleaned = super().clean()
        pedagogico = cleaned.get('consentimiento_pedagogico')
        if pedagogico == 'true':
            # Con consentimiento pedagógico, se esperan respuestas en Q9/Q10
            # si el campo fue enviado (tipo completa). Si no fue enviado (tipo
            # básica), la vista lo autocompleta en False.
            pass
        return cleaned

    def cleaned_pedagogico(self):
        return self.cleaned_data.get('consentimiento_pedagogico') == 'true'

    def cleaned_investigacion(self):
        return self.cleaned_data.get('consentimiento_investigacion') == 'true'

    def cleaned_contacto(self):
        return self.cleaned_data.get('consentimiento_contacto_seguimiento') == 'true'


class EncuestaForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.tipo = kwargs.pop('tipo', 'basica')
        readonly_fields = kwargs.pop('readonly_fields', set())
        super().__init__(*args, **kwargs)

        placeholder = '— Seleccioná tu carrera —'
        labels = dict(CARRERA_CHOICES)
        carreras_unificadas = get_carreras_unificadas_por_clave()
        self.fields['carrera_uba_anterior'].choices = [
            ('', placeholder),
            *[(clave, labels.get(clave, clave)) for clave in carreras_unificadas],
        ]

        for field_name in readonly_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs['disabled'] = True

    """Formulario de encuesta socioeducativa de onboarding.

    Cubre las preguntas Q2-Q7 (datos básicos) y, para tipo='completa',
    Q11-Q48 (facultad/carrera, situación socioeducativa, lógica).
    Todos los campos son required=False porque la visibilidad de cada
    sección depende de respuestas anteriores (JS branching).
    """

    # ── Datos básicos (siempre presentes) ────────────────────────────────
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label='Apellido/s',
    )
    first_name = forms.CharField(
        max_length=150,
        required=True,
        label='Nombre/s',
    )
    email = forms.EmailField(
        required=False,
        label='Correo electrónico (opcional)',
    )
    dni = forms.CharField(
        max_length=20,
        required=True,
        label='DNI',
    )
    whatsapp = forms.CharField(
        max_length=20,
        required=False,
        label='WhatsApp (sin 0 y sin 15)',
    )
    fecha_nacimiento = forms.DateField(
        required=False,
        label='Fecha de nacimiento',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    # ── Facultad y carrera (tipo completa) ───────────────────────────────
    facultad = forms.ChoiceField(
        choices=[('', '— Seleccioná tu facultad —')] + FACULTAD_CHOICES,
        required=False,
        label='Facultad',
    )
    carrera = forms.ChoiceField(
        choices=[('', '— Seleccioná tu carrera —')] + CARRERA_CHOICES,
        required=False,
        label='Carrera',
    )

    # ── Geografía (tipo completa) ─────────────────────────────────────────
    origen_caba_gba = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Tu lugar de origen es la Ciudad de Buenos Aires o el Gran Buenos Aires?',
    )
    vive_en = forms.ChoiceField(
        choices=[('caba', 'Ciudad de Buenos Aires'), ('gba', 'Gran Buenos Aires')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Vivís en la Ciudad de Buenos Aires o en el Gran Buenos Aires?',
    )
    mudado_con_familia = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Te mudaste al AMBA con tu familia?',
    )
    mudado_para_trabajar_estudiar = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Te mudaste al AMBA para trabajar y/o estudiar?',
    )
    tiempo_mudado = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('menos_1', 'Menos de 1 año'),
            ('1_2', '1 año'),
            ('2_5', '2-3 años'),
            ('mas_5', 'Más de 3 años'),
        ],
        required=False,
        label='¿Hace cuánto tiempo te mudaste al AMBA?',
    )
    desde_donde = forms.ChoiceField(
        choices=[
            ('argentina', 'Desde otra parte de la Argentina'),
            ('fuera_argentina', 'Desde fuera de la Argentina'),
        ],
        required=False,
        widget=forms.RadioSelect,
        label='¿Desde dónde te mudaste?',
    )
    provincia_origen = forms.ChoiceField(
        choices=[('', '— Seleccioná tu provincia —')] + PROVINCIA_CHOICES,
        required=False,
        label='¿Desde qué provincia te mudaste?',
    )
    pais_origen = forms.CharField(
        max_length=100,
        required=False,
        label='Indicanos desde qué país te mudaste',
    )

    # ── Situación personal (tipo completa) ───────────────────────────────
    necesita_adecuacion = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Hay alguna adecuación, apoyo o consideración particular que necesites para cursar o rendir esta materia?',
    )
    tiene_cud = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Tenés Certificado Único de Discapacidad (CUD)?',
    )
    con_quien_vive = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('solo', 'Vivo sola/e/o'),
            ('familia_nuclear', 'Vivo en la vivienda familiar'),
            ('residencia', 'Comparto vivienda con otras personas, fuera de la vivienda familiar (vivienda compartida, alojamiento, hotel, etc.)'),
        ],
        required=False,
        label='¿Con quién vivís?',
    )
    tiempo_viaje_puan = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('menos_30', 'Menos de 30 minutos'),
            ('30_60', '30 min - 1 hora'),
            ('mas_90', 'Más de 1 hora'),
        ],
        required=False,
        label='¿Cuánto tiempo de viaje tenés hasta tu sede del CBC?',
    )
    situacion_laboral = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('no_trabajo', 'No trabajo y no estoy buscando'),
            ('busco', 'Busco trabajo'),
            ('hasta_4', 'Trabajo hasta 4 horas por día'),
            ('4_6', 'Trabajo entre 4 y 6 horas por día'),
            ('mas_6', 'Trabajo 6 o más horas por día'),
        ],
        required=False,
        label='Situación laboral',
    )
    dias_trabaja = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('no', 'No trabajo'),
            ('menos_5', 'Trabajo menos de 5 días a la semana'),
            ('5', 'Trabajo 5 días de la semana'),
            ('mas_5', 'Trabajo más de 5 días a la semana'),
        ],
        required=False,
        label='¿Cuántos días por semana trabajás?',
    )
    acceso_internet = forms.MultipleChoiceField(
        choices=_INTERNET_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Acceso a internet',
    )
    # Dispositivos — un campo por dispositivo; la vista los serializa a JSON
    dispositivo_celular = forms.ChoiceField(
        choices=_DISPOSITIVO_CHOICES,
        required=False,
        widget=forms.RadioSelect,
        label='Celular',
    )
    dispositivo_tablet = forms.ChoiceField(
        choices=_DISPOSITIVO_CHOICES,
        required=False,
        widget=forms.RadioSelect,
        label='Tablet',
    )
    dispositivo_pc = forms.ChoiceField(
        choices=_DISPOSITIVO_CHOICES,
        required=False,
        widget=forms.RadioSelect,
        label='PC de escritorio',
    )
    dispositivo_laptop = forms.ChoiceField(
        choices=_DISPOSITIVO_CHOICES,
        required=False,
        widget=forms.RadioSelect,
        label='Notebook/laptop',
    )

    # ── Secundaria (tipo completa) ────────────────────────────────────────
    tiempo_desde_secundaria = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('menos_1', 'Menos de un año'),
            ('1_3', 'Entre 1 y 3 años'),
            ('mas_3', 'Más de 3 años'),
        ],
        required=False,
        label='¿Hace cuánto tiempo terminaste la escuela secundaria?',
    )
    tipo_escuela = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
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
        required=False,
        label='¿De qué tipo de escuela te recibiste?',
    )

    # ── Estudios superiores (tipo completa) ──────────────────────────────
    estudios_superiores = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('no', 'No'),
            ('si_uba', 'Sí, en la UBA'),
            ('si_fuera_uba', 'Sí, fuera de la UBA'),
        ],
        required=False,
        label='¿Tenés estudios superiores previos?',
    )
    carrera_uba_anterior = forms.ChoiceField(
        choices=[('', '— Seleccioná tu carrera —')] + CARRERA_CHOICES,
        required=False,
        label='¿Qué carrera cursaste en la UBA?',
    )
    termino_cbc_anterior = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Terminaste el CBC de esa carrera?',
    )
    se_recibio_uba = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Te recibiste de esa carrera?',
    )
    tipo_inst_fuera_uba = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('universidad', 'Universidad'),
            ('formacion_tecnica', 'Instituto de Formación Técnica Superior'),
            ('profesorado', 'Profesorado'),
            ('otras', 'Otras'),
        ],
        required=False,
        label='¿En qué tipo de institución estudiaste?',
    )
    tipo_inst_fuera_uba_otras = forms.CharField(
        max_length=100,
        required=False,
        label='Otras (especificar)',
    )
    carrera_fuera_uba = forms.CharField(
        max_length=100,
        required=False,
        label='¿Qué carrera cursaste fuera de la UBA?',
    )
    se_recibio_fuera_uba = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Te recibiste?',
    )

    # ── CBC (tipo completa) ───────────────────────────────────────────────
    hizo_uba_xxi = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Hiciste UBA XXI?',
    )
    tiempo_en_cbc = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('primero', 'Éste es mi primer cuatrimestre'),
            ('segundo', 'Éste es mi segundo cuatrimestre'),
            ('1_2_anios', 'Entre 1 y 2 años'),
            ('mas_2_anios', 'Más de 2 años'),
        ],
        required=False,
        label='¿Hace cuánto tiempo estás en el CBC?',
    )
    interrupcion_cbc = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('un_cuatr', 'Sí, un cuatrimestre'),
            ('mas', 'Sí, más de un cuatrimestre'),
            ('no', 'No'),
        ],
        required=False,
        label='¿Interrumpiste el CBC alguna vez?',
    )
    ya_curso_ipc = forms.ChoiceField(
        choices=[('true', 'Sí'), ('false', 'No')],
        required=False,
        widget=forms.RadioSelect,
        label='¿Ya cursaste IPC antes?',
    )
    motivo_no_termino_ipc = forms.ChoiceField(
        choices=[
            ('', '— Seleccioná —'),
            ('personal', 'Dejé la materia por motivos personales'),
            ('laboral', 'Dejé la materia por motivos laborales'),
            ('priorice', 'Priorizé la aprobación de otras materias'),
            ('ausencias', 'Perdí la regularidad por ausencias'),
            ('promedio', 'No alcancé el promedio necesario para rendir el examen final'),
            ('final', 'No logré aprobar el examen final'),
            ('vencio', 'Se me venció la materia'),
            ('otra', 'Otras'),
        ],
        required=False,
        label='¿Por qué no pudiste terminar la materia?',
    )
    motivo_no_termino_ipc_otras = forms.CharField(
        max_length=255,
        required=False,
        label='Otras (especificar)',
    )
    materias_aprobadas = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=5,
        label='¿Cuántas materias del CBC aprobaste hasta ahora?',
    )

    # ── Lógica y polémica (tipo completa) ────────────────────────────────
    acertijo_silogismo = forms.ChoiceField(
        choices=[
            ('mas_alto', 'Más alto'),
            ('mas_bajo', 'Más bajo'),
        ],
        required=False,
        widget=forms.RadioSelect,
        label='Si María habla más bajo que Carmen y Lola habla más alto que Carmen, ¿María habla más alto o más bajo que Lola?',
    )
    acertijo_cirugia_no_se = forms.ChoiceField(
        choices=[('true', 'No sé')],
        required=False,
        widget=forms.RadioSelect,
        label='Un padre y un hijo viajan en coche y tienen un accidente… la persona que tiene que operarlo dice: “Lo siento, no puedo operarlo. Es mi hijo.” ¿Por qué?',
    )
    acertijo_cirugia = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(),
        label='Respuesta breve',
    )
    acertijo_hilera = forms.ChoiceField(
        choices=[
            ('rodriguez', 'La familia Rodríguez'),
            ('rivera', 'La familia Rivera'),
            ('posada', 'La familia Posada'),
        ],
        required=False,
        widget=forms.RadioSelect,
        label='En una hilera de cuatro casas la familia Rodríguez vive al lado de la familia Posada, pero no al lado de la familia Rivera. Si la familia Rivera no vive al lado de la familia Martínez, ¿qué familia es vecina inmediata de la familia Martínez?',
    )
    articulo_risa = forms.ChoiceField(
        choices=[('true', 'Lo creo'), ('false', 'No lo creo')],
        required=False,
        widget=forms.RadioSelect,
        label='El sitio Xataka Ciencia publicó un artículo con el siguiente título: “La risa no una expresión exclusivamente humana: ya se han logrado documentar risas en al menos 65 especies de animales diferentes”. ¿Lo creés o no?',
    )
    que_es_ciencia = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
        label='En una oración ¿Qué es la ciencia?',
    )

    def clean(self):
        cleaned = super().clean()
        if self.tipo == 'completa':
            for campo in ('facultad', 'carrera'):
                if not cleaned.get(campo):
                    self.add_error(campo, 'Este campo es obligatorio.')

        tipo_inst = cleaned.get('tipo_inst_fuera_uba')
        tipo_inst_otras = (cleaned.get('tipo_inst_fuera_uba_otras') or '').strip()
        if tipo_inst == 'otras':
            cleaned['tipo_inst_fuera_uba'] = tipo_inst_otras
        elif tipo_inst:
            cleaned['tipo_inst_fuera_uba'] = dict(self.fields['tipo_inst_fuera_uba'].choices).get(tipo_inst, tipo_inst)
        else:
            cleaned['tipo_inst_fuera_uba'] = ''
        cleaned['tipo_inst_fuera_uba_otras'] = ''

        if cleaned.get('termino_cbc_anterior') != 'true':
            cleaned['se_recibio_uba'] = ''

        motivo = cleaned.get('motivo_no_termino_ipc')
        motivo_otras = (cleaned.get('motivo_no_termino_ipc_otras') or '').strip()
        if motivo == 'otra':
            cleaned['motivo_no_termino_ipc'] = motivo_otras
        elif motivo:
            cleaned['motivo_no_termino_ipc'] = dict(self.fields['motivo_no_termino_ipc'].choices).get(motivo, motivo)
        else:
            cleaned['motivo_no_termino_ipc'] = ''
        cleaned['motivo_no_termino_ipc_otras'] = ''

        if cleaned.get('acertijo_cirugia_no_se') == 'true':
            cleaned['acertijo_cirugia'] = 'No sé'
        elif not cleaned.get('acertijo_cirugia'):
            cleaned['acertijo_cirugia'] = ''
        return cleaned
