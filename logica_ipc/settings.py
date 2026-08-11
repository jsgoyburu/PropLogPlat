"""
Django settings para logica_ipc.

Configuración en dos modos:
  - Desarrollo local: DEBUG=True, SQLite (fallback si DATABASE_URL no está).
  - Producción (Railway): DEBUG=False, Postgres vía DATABASE_URL.

Variables de entorno requeridas en producción:
  SECRET_KEY, DEBUG, DATABASE_URL, ALLOWED_HOSTS
Ver .env.example para la lista completa.
"""

import os
from pathlib import Path

import dj_database_url

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    'SECRET_KEY'
)

# Protege el asistente web de primera instalación. En desarrollo puede quedar
# vacío; en producción el instalador se niega a crear un admin sin esta clave.
SETUP_TOKEN = os.environ.get('SETUP_TOKEN', '').strip()

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# ALLOWED_HOSTS: se construye desde la variable de entorno ALLOWED_HOSTS
# más el dominio que Railway inyecta automáticamente en RAILWAY_PUBLIC_DOMAIN.
_allowed_env = os.environ.get('ALLOWED_HOSTS', '')
_allowed_hosts = [h.strip() for h in _allowed_env.split(',') if h.strip()]

_railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if _railway_domain and _railway_domain not in _allowed_hosts:
    _allowed_hosts.append(_railway_domain)

ALLOWED_HOSTS = _allowed_hosts or ['localhost', '127.0.0.1']

# CSRF_TRUSTED_ORIGINS: solo necesario en producción (Railway/HTTPS).
# En desarrollo (DEBUG=True) Django no requiere esta lista para localhost.
_csrf_env = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
_csrf_origins = [o.strip() for o in _csrf_env.split(',') if o.strip()]

for _host in ALLOWED_HOSTS:
    if _host not in ('localhost', '127.0.0.1'):
        _origin = f'https://{_host}'
        if _origin not in _csrf_origins:
            _csrf_origins.append(_origin)

if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = _csrf_origins

# ---------------------------------------------------------------------------
# Aplicaciones
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    # Django contrib
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Terceros
    'rest_framework',
    'django_ckeditor_5',
    # Apps del proyecto
    'accounts',
    'cursos',
    'ejercicios',
    'analiticas',
    'docentes',
    # motor no se registra: es Python puro, sin modelos Django
]

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # static files en producción
    'django.contrib.sessions.middleware.SessionMiddleware',
    'accounts.middleware.IdiomaSitioMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.middleware.ForzarCambioPasswordMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'logica_ipc.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.config_sitio',
            ],
        },
    },
]

WSGI_APPLICATION = 'logica_ipc.wsgi.application'

# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
# En desarrollo sin DATABASE_URL: SQLite local.
# En Railway: DATABASE_URL se inyecta automáticamente → Postgres.

_db_url = os.environ.get('DATABASE_URL')
_en_railway = bool(os.environ.get('RAILWAY_ENVIRONMENT'))
_usar_database_url = (
    _en_railway
    or not DEBUG
    or os.environ.get('USE_DATABASE_URL', 'False') == 'True'
)

if _db_url and _usar_database_url:
    # En producción (Railway u otro proveedor): usar la base administrada.
    DATABASES = {
        'default': dj_database_url.config(
            default=_db_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Desarrollo local: SQLite. USE_DATABASE_URL=True permite probar Postgres.
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

import sys as _sys

_redis_url = os.environ.get('REDIS_URL')

if 'test' in _sys.argv or 'pytest' in _sys.modules:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
elif _redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _redis_url,
        }
    }
else:
    # Sin REDIS_URL (desarrollo local o Railway sin plugin Redis): LocMemCache.
    # El sitio funciona correctamente; las analíticas no se cachean entre workers.
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# ---------------------------------------------------------------------------
# Modelo de usuario personalizado
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = 'accounts.Usuario'

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# ---------------------------------------------------------------------------
# Validación de contraseñas
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Internacionalización
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'es'
LANGUAGES = [
    ('es', 'Castellano'),
    ('en', 'English'),
    ('fr', 'Français'),
    ('de', 'Deutsch'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Archivos estáticos
# ---------------------------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------------------
# Clave primaria por defecto
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# URLs de autenticación
# ---------------------------------------------------------------------------

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ---------------------------------------------------------------------------
# Seguridad HTTPS (solo en producción)
# ---------------------------------------------------------------------------

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

customColorPalette = [
    {
        'color': 'hsl(4, 90%, 58%)',
        'label': 'Red'
    },
    {
        'color': 'hsl(340, 82%, 52%)',
        'label': 'Pink'
    },
    {
        'color': 'hsl(291, 64%, 42%)',
        'label': 'Purple'
    },
    {
        'color': 'hsl(262, 52%, 47%)',
        'label': 'Deep Purple'
    },
    {
        'color': 'hsl(231, 48%, 48%)',
        'label': 'Indigo'
    },
    {
        'color': 'hsl(207, 90%, 54%)',
        'label': 'Blue'
    },
]

CKEDITOR_5_CONFIGS = {
'default': {
    'toolbar': {
        'items': ['heading', '|', 'bold', 'italic', 'link',
                    'bulletedList', 'numberedList', 'blockQuote', 'imageUpload', ],
                }

},
'extends': {
    'blockToolbar': [
        'paragraph', 'heading1', 'heading2', 'heading3',
        '|',
        'bulletedList', 'numberedList',
        '|',
        'blockQuote',
    ],
    'toolbar': {
        'items': ['heading', '|', 'outdent', 'indent', '|', 'bold', 'italic', 'link', 'underline', 'strikethrough',
                    'code','subscript', 'superscript', 'highlight', '|', 'codeBlock', 'sourceEditing', 'insertImage',
                'bulletedList', 'numberedList', 'todoList', '|',  'blockQuote', 'imageUpload', '|',
                'fontSize', 'fontFamily', 'fontColor', 'fontBackgroundColor', 'mediaEmbed', 'removeFormat',
                'insertTable',
                ],
        'shouldNotGroupWhenFull': 'true'
    },
    'image': {
        'toolbar': ['imageTextAlternative', '|', 'imageStyle:alignLeft',
                    'imageStyle:alignRight', 'imageStyle:alignCenter', 'imageStyle:side',  '|'],
        'styles': [
            'full',
            'side',
            'alignLeft',
            'alignRight',
            'alignCenter',
        ]

    },
    'table': {
        'contentToolbar': [ 'tableColumn', 'tableRow', 'mergeTableCells',
        'tableProperties', 'tableCellProperties' ],
        'tableProperties': {
            'borderColors': customColorPalette,
            'backgroundColors': customColorPalette
        },
        'tableCellProperties': {
            'borderColors': customColorPalette,
            'backgroundColors': customColorPalette
        }
    },
    'heading' : {
        'options': [
            { 'model': 'paragraph', 'title': 'Paragraph', 'class': 'ck-heading_paragraph' },
            { 'model': 'heading1', 'view': 'h1', 'title': 'Heading 1', 'class': 'ck-heading_heading1' },
            { 'model': 'heading2', 'view': 'h2', 'title': 'Heading 2', 'class': 'ck-heading_heading2' },
            { 'model': 'heading3', 'view': 'h3', 'title': 'Heading 3', 'class': 'ck-heading_heading3' }
        ]
    }
},
'list': {
    'properties': {
        'styles': 'true',
        'startIndex': 'true',
        'reversed': 'true',
    }
}
}

# Define a constant in settings.py to specify file upload permissions
CKEDITOR_5_FILE_UPLOAD_PERMISSION = "staff"  # Possible values: "staff", "authenticated", "any"
