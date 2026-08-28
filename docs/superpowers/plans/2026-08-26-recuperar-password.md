# Autorecuperación de contraseña por email — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cualquier usuario pueda recuperar su contraseña solo, con un link firmado que le llega por mail, sirve una sola vez y vence a las 24 horas.

**Architecture:** Se apoya entero en `django.contrib.auth`, que ya trae las cuatro vistas y el generador de tokens. Se agregan dos subclases finas para lo que Django no cubre —el nombre del sitio en el mail y el throttling en una, y la limpieza de `debe_cambiar_password` en la otra—, seis templates en castellano y un bloque de configuración de email que hoy no existe. Sin modelos nuevos, **sin migraciones**.

**Tech Stack:** Django 6.0.6 · `django.contrib.auth.views` · `django.contrib.auth.tokens.PasswordResetTokenGenerator` · backend SMTP por variables de entorno · cache de Django (Redis en producción, LocMem en local y en tests).

Spec: [`docs/superpowers/specs/2026-08-26-recuperar-password-design.md`](../specs/2026-08-26-recuperar-password-design.md)

## Global Constraints

- **No agregar dependencias.** `requirements.txt` está pinneado a propósito desde que el rebuild del 2026-08-07 tiró abajo los dos servicios. Este trabajo no toca ese archivo.
- **Sin migraciones.** No se modifica ningún modelo. Si aparece una migración, algo se hizo mal.
- **Python del proyecto:** `C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe` (el venv está en el directorio *padre* del repo).
- **Correr tests siempre con `SECRET_KEY` seteada.** El `.env` vive en el directorio padre y no se carga solo.
- **Comando de tests de esta app:**
  ```bash
  SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts
  ```
- **Baseline verde antes de empezar:** `accounts` da `Ran 24 tests ... OK`. Cada task suma tests; ninguno debe romper los 24 previos.
- **Anti-enumeración innegociable.** Ninguna respuesta puede revelar si una dirección está registrada. Ante mail desconocido, cuenta inactiva o throttle excedido, el usuario ve **exactamente** la misma pantalla que ante un envío exitoso.
- **Idioma:** todo el texto visible y los comentarios de código, en castellano rioplatense (`vos`, no `tú`).
- **Rama:** `claude/recuperar-password`.

## Estructura de archivos

| Archivo | Responsabilidad | Task |
|---|---|---|
| `logica_ipc/settings.py` | backend de mail + `PASSWORD_RESET_TIMEOUT` | 1 |
| `.env.example` · `README.md` | documentar las 7 variables nuevas | 1 |
| `accounts/urls.py` | las 4 rutas, con `success_url` namespaceado | 2 |
| `accounts/views.py` | `PasswordResetSitioView` (nombre del sitio + throttle) y `PasswordResetConfirmLimpiaFlagView` (limpia el flag) | 2, 4, 5 |
| `templates/registration/password_reset_*.html` · `_subject.txt` | las 4 pantallas + asunto y cuerpo del mail | 2 |
| `templates/registration/login.html` | link de entrada al flujo | 6 |
| `accounts/tests.py` | los 21 casos | 2–6 |
| `AGENTS.md` · `MEMORY.md` | estado funcional + bitácora | 7 |

---

### Task 1: Configuración de email y vencimiento a 24 h

Hoy el proyecto no tiene **ninguna** configuración de email: no hay `EMAIL_BACKEND`, ni `DEFAULT_FROM_EMAIL`, ni un solo `send_mail`. Este task construye ese piso. Sin él, ningún otro task puede mandar nada.

**Files:**
- Modify: `logica_ipc/settings.py` (insertar entre el bloque *Cache* y el bloque *Modelo de usuario personalizado*)
- Modify: `.env.example`
- Modify: `README.md` (sección *Variables de entorno*, aprox. línea 154)
- Test: `accounts/tests.py`

**Interfaces:**
- Consumes: nada.
- Produces: `settings.PASSWORD_RESET_TIMEOUT == 86400`, `settings.EMAIL_TIMEOUT == 10`, `settings.DEFAULT_FROM_EMAIL` (str). Los tasks 2–6 dependen de que el timeout sea ése.

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `accounts/tests.py`. El import de `settings` va arriba, junto a los otros imports del módulo:

```python
from django.conf import settings
```

```python
class ConfiguracionRecuperarPasswordTests(TestCase):
    """El vencimiento del link es el requisito literal del pedido: 24 horas.

    Django trae 259200 (3 días) por defecto. Si alguien borra el override en
    settings.py, el flujo sigue andando y los links siguen llegando: lo único
    que cambia es que duran tres días en vez de uno. Es exactamente el tipo de
    regresión que no se nota, así que se fija con un test.
    """

    def test_el_link_vence_a_las_24_horas(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 60 * 60 * 24)

    def test_hay_timeout_de_smtp(self):
        # Sin timeout, un SMTP que no responde deja colgado un worker de
        # gunicorn hasta que el sistema operativo corte el socket.
        self.assertEqual(settings.EMAIL_TIMEOUT, 10)

    def test_hay_remitente_por_defecto(self):
        self.assertTrue(settings.DEFAULT_FROM_EMAIL)
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.ConfiguracionRecuperarPasswordTests
```

Esperado: FAIL. `test_el_link_vence_a_las_24_horas` con `259200 != 86400`, y `test_hay_timeout_de_smtp` con `AttributeError` o `None != 10` (el default de Django para `EMAIL_TIMEOUT` es `None`).

- [ ] **Step 3: Escribir la configuración**

En `logica_ipc/settings.py`, insertar este bloque **entre** el final del bloque `# Cache` (después del `else:` que define `LocMemCache`) y el comentario `# Modelo de usuario personalizado`:

```python
# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# Se usa para la recuperación de contraseña (django.contrib.auth).
#
# El backend se elige por presencia de EMAIL_HOST:
#   - con EMAIL_HOST → SMTP real.
#   - sin EMAIL_HOST → consola: el mail se imprime en la terminal, con el link
#     clickeable. Permite probar el flujo entero en local sin credenciales.
#
# Se eligió SMTP genérico y no la API HTTP de un proveedor: por esta misma
# puerta entran Gmail (con app password), Resend, SendGrid, Brevo y Mailgun.
# Cambiar de proveedor es cambiar variables de entorno, no código, y no suma
# dependencias a requirements.txt.

EMAIL_HOST = os.environ.get('EMAIL_HOST', '')

if EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
    EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False') == 'True'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Sin timeout explícito, un SMTP que no responde bloquea un worker de gunicorn
# hasta el timeout de socket del sistema operativo.
EMAIL_TIMEOUT = 10

DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL', 'IPC · Lógica <no-reply@localhost>'
)

# Vencimiento del link de recuperación de contraseña.
# Django trae 259200 (3 días); el pedido es de 24 horas.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24
```

- [ ] **Step 4: Correr el test y verificar que pasa**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.ConfiguracionRecuperarPasswordTests
```

Esperado: `Ran 3 tests ... OK`.

- [ ] **Step 5: Verificar que Django arranca y no apareció ninguna migración**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py makemigrations --check --dry-run
```

Esperado: `No changes detected`. Si detecta cambios, se tocó un modelo por error.

- [ ] **Step 6: Documentar las variables en `.env.example`**

Agregar al final del archivo:

```bash
# ── Email (recuperación de contraseña) ────────────────────────────────────────
# Sin EMAIL_HOST, los mails se imprimen en la consola en vez de enviarse.
# Eso alcanza para desarrollo: el link de recuperación sale en la terminal.
#
# Para producción sirve cualquier proveedor SMTP. Ejemplo con Brevo, que da
# 300 mails por día gratis y no requiere app password de Google:
# EMAIL_HOST=smtp-relay.brevo.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=tu-mail-de-login-de-brevo
# EMAIL_HOST_PASSWORD=la-smtp-key-generada-en-el-panel
# EMAIL_USE_TLS=True
#
# OJO: la password es una "SMTP key" que se genera en el panel de Brevo, NO la
# contraseña de la cuenta.
#
# EMAIL_USE_SSL solo si el proveedor usa el puerto 465. Es mutuamente
# excluyente con EMAIL_USE_TLS: si ponés SSL en True, poné TLS en False, o
# Django levanta ImproperlyConfigured al arrancar.
# EMAIL_USE_SSL=False

# Remitente que ve quien recibe el mail. Lo que va acá decide si los mails
# llegan a la bandeja o a spam, y es la única parte de esta configuración que
# NO es indistinta:
#
#   - Con dominio propio (recomendado): autenticarlo en el proveedor con SPF y
#     DKIM y usar una dirección de ese dominio. SPF y DKIM alinean, DMARC pasa,
#     el mail llega.
#         DEFAULT_FROM_EMAIL=IPC · Lógica <no-reply@tu-dominio.com>
#
#   - Sin dominio propio: se puede verificar una dirección suelta (un Gmail)
#     con un código de 6 dígitos y usarla de remitente. Manda, pero SPF y DKIM
#     fallan porque nadie puede firmar por gmail.com. La política DMARC de
#     gmail.com es p=none, así que no lo rechazan, pero sube mucho la chance de
#     spam -sobre todo en Gmail, que sabe que ese mail no salió de Google-.
#         DEFAULT_FROM_EMAIL=IPC · Lógica <tu-cuenta@gmail.com>
#
# El dominio generado por Railway (*.up.railway.app) NO sirve de remitente:
# Railway es dueño de esa zona DNS, así que no se le pueden cargar SPF ni DKIM,
# no hay casilla donde recibir el código de verificación y no hay dónde caigan
# los rebotes.
#
# Cambiar de un caso al otro es editar estas variables. No se toca código.
```

- [ ] **Step 7: Documentar las variables en `README.md`**

En la sección *Variables de entorno*, debajo de la línea de `GROQ_API_KEY`, agregar:

```markdown
Email (recuperación de contraseña):

- `EMAIL_HOST` (opcional; sin ella los mails se imprimen en consola en vez de enviarse)
- `EMAIL_PORT` (default `587`)
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS` (default `True`)
- `EMAIL_USE_SSL` (default `False`; mutuamente excluyente con `EMAIL_USE_TLS`)
- `DEFAULT_FROM_EMAIL` (remitente visible)

Sirve cualquier proveedor SMTP. Brevo da 300 mails/día gratis y no pide app
password de Google (`smtp-relay.brevo.com:587`, usuario = mail de login,
password = *SMTP key* del panel).

`DEFAULT_FROM_EMAIL` es la única de estas variables que no es indistinta:
decide si los mails llegan a la bandeja o a spam. Con dominio propio
autenticado (SPF + DKIM) llegan. Con un Gmail verificado como remitente
suelto también se manda, pero SPF y DKIM fallan y sube la chance de spam. El
dominio generado por Railway no sirve de remitente: no se le pueden cargar
registros DNS. Cambiar de un caso al otro es editar variables, no código.
```

- [ ] **Step 8: Commit**

```bash
git add logica_ipc/settings.py accounts/tests.py .env.example README.md
git commit -m "feat(auth): configuracion de email y vencimiento de reset a 24 h"
```

---

### Task 2: El flujo completo de recuperación

Cablea las cuatro vistas, escribe los seis templates y deja el flujo andando de punta a punta.

**Files:**
- Modify: `accounts/views.py`
- Modify: `accounts/urls.py`
- Create: `templates/registration/password_reset_form.html`
- Create: `templates/registration/password_reset_done.html`
- Create: `templates/registration/password_reset_confirm.html`
- Create: `templates/registration/password_reset_complete.html`
- Create: `templates/registration/password_reset_email.html`
- Create: `templates/registration/password_reset_subject.txt`
- Test: `accounts/tests.py`

**Interfaces:**
- Consumes: `settings.PASSWORD_RESET_TIMEOUT` (Task 1).
- Produces:
  - `accounts.views.PasswordResetSitioView` — subclase de `PasswordResetView`. El Task 5 le agrega el throttle.
  - Rutas con nombre: `accounts:password_reset`, `accounts:password_reset_done`, `accounts:password_reset_confirm` (kwargs `uidb64`, `token`), `accounts:password_reset_complete`.
  - En `accounts/tests.py`, la clase `RecuperarPasswordFlujoTests` con el helper `_link_de_reset(self) -> str`, que extrae la ruta del link del último mail. Los tasks 3 y 4 definen su propia copia adaptada a su usuario: son clases `TestCase` independientes y el plan repite el código a propósito, para que cada task se pueda leer y ejecutar solo.

> **Trampa a evitar.** `accounts/urls.py` declara `app_name = 'accounts'`, pero las vistas de Django resuelven sus destinos **sin** namespace: `PasswordResetView.success_url = reverse_lazy("password_reset_done")` y `PasswordResetConfirmView.success_url = reverse_lazy("password_reset_complete")`. Si no se pisan con `reverse_lazy('accounts:...')`, el flujo explota con `NoReverseMatch` recién al enviar el formulario, no al arrancar el servidor. Lo mismo vale para el `{% url %}` del template del mail.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `accounts/tests.py`. Estos imports van arriba del módulo, junto a los que ya están:

```python
from django.core import mail
from django.core.cache import cache
```

```python
class RecuperarPasswordFlujoTests(TestCase):
    """El camino feliz, y la garantía de que no se filtra quién está registrado."""

    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username='est_olvido',
            email='olvido@ejemplo.com',
            password='clave-vieja-123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        # El throttle del Task 5 cuenta en cache y es global al proceso:
        # sin esto, un test le deja el contador cargado al siguiente.
        cache.clear()

    def _link_de_reset(self, email='olvido@ejemplo.com'):
        """Pide un reset y devuelve la ruta del link que llegó por mail."""
        self.client.post(reverse('accounts:password_reset'), {'email': email})
        self.assertTrue(mail.outbox, 'No llegó ningún mail.')
        for palabra in mail.outbox[-1].body.split():
            if '/accounts/reset/' in palabra:
                return palabra[palabra.index('/accounts/reset/'):]
        self.fail('El mail no contiene ningún link de reset.')

    def test_pedido_con_mail_registrado_manda_un_mail_con_el_link(self):
        response = self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'olvido@ejemplo.com'},
        )

        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['olvido@ejemplo.com'])

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.assertIn(f'/accounts/reset/{uid}/', mail.outbox[0].body)

    def test_el_mail_avisa_que_vence_y_que_es_de_un_solo_uso(self):
        # Es lo que le permite a la persona entender por qué el link dejó de
        # andar, en vez de pensar que el sistema se rompió.
        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'olvido@ejemplo.com'},
        )
        cuerpo = mail.outbox[0].body
        self.assertIn('24 horas', cuerpo)
        self.assertIn('una sola vez', cuerpo)

    def test_pedido_con_mail_desconocido_no_manda_nada_y_no_lo_dice(self):
        response = self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'nadie@ejemplo.com'},
        )

        # Misma redirección que el caso exitoso: el formulario no sirve para
        # averiguar qué direcciones están registradas en la plataforma.
        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_flujo_completo_cambia_la_clave_y_permite_entrar(self):
        link = self._link_de_reset()

        # El GET no muestra el formulario: guarda el token en sesión y redirige
        # a .../set-password/, para no filtrarlo por el header Referer.
        response = self.client.get(link)
        self.assertEqual(response.status_code, 302)
        url_formulario = response['Location']
        self.assertIn('set-password', url_formulario)

        response = self.client.post(url_formulario, {
            'new_password1': 'clave-nueva-456',
            'new_password2': 'clave-nueva-456',
        })
        self.assertRedirects(response, reverse('accounts:password_reset_complete'))

        self.assertTrue(
            self.client.login(username='est_olvido', password='clave-nueva-456')
        )

    def test_uid_corrupto_muestra_el_aviso_de_link_invalido(self):
        response = self.client.get(
            reverse('accounts:password_reset_confirm',
                    kwargs={'uidb64': 'basura', 'token': 'mas-basura'})
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['validlink'])
        self.assertContains(response, 'Este link ya no sirve')
```

Y estos imports, también arriba del módulo:

```python
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordFlujoTests
```

Esperado: los 5 fallan con `NoReverseMatch: 'password_reset' is not a valid view function or pattern name`.

- [ ] **Step 3: Escribir la vista**

En `accounts/views.py`, agregar el import arriba (junto a los que ya están):

```python
from django.contrib.auth import views as auth_views
```

Y la clase, después de `LoginConPrimerAccesoView`:

```python
class PasswordResetSitioView(auth_views.PasswordResetView):
    """PasswordResetView con el nombre del sitio en el mail.

    Los templates de mail se renderizan con ``render_to_string``, sin request,
    así que los context processors no corren y ``config_sitio`` no está
    disponible como en el resto de los templates. El nombre se inyecta acá.

    Va en ``form_valid`` y no en la definición de la URL a propósito: leer
    ConfigSitio al importar el URLconf sería pegarle a la base antes de que
    las apps estén listas.
    """

    def form_valid(self, form):
        self.extra_email_context = {
            'nombre_sitio': ConfigSitio.get().nombre_sitio,
        }
        return super().form_valid(form)
```

`ConfigSitio` ya está importado en `accounts/views.py` (lo usa `favicon_view`). Verificarlo antes de agregar un import duplicado.

- [ ] **Step 4: Escribir las URLs**

En `accounts/urls.py`, cambiar la primera línea de import por:

```python
from django.urls import path, reverse_lazy
```

Y agregar estas cuatro rutas al final de `urlpatterns`:

```python
    # Recuperación de contraseña. `success_url` va explícito porque las vistas
    # de Django lo resuelven sin namespace (reverse_lazy("password_reset_done"))
    # y esta app declara app_name = 'accounts'.
    path(
        'password_reset/',
        views.PasswordResetSitioView.as_view(
            success_url=reverse_lazy('accounts:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password_reset/enviado/',
        auth_views.PasswordResetDoneView.as_view(),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/completo/',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),
```

- [ ] **Step 5: Escribir los cuatro templates de pantalla**

`templates/registration/password_reset_form.html`:

```django
{% extends "base.html" %}

{% block title %}Recuperar contraseña — {{ config_sitio.nombre_sitio }}{% endblock %}

{% block content %}
<div class="container" style="max-width: 420px;">
  <div class="card" style="margin-top: 3rem;">
    <h2 style="margin-top: 0; margin-bottom: 0.75rem;">Recuperar contraseña</h2>

    <p style="font-size: 0.9rem; color: #666; margin-bottom: 1.5rem;">
      Escribí el correo electrónico con el que te registraste. Te mandamos un
      link para elegir una contraseña nueva.
    </p>

    <form method="post" novalidate>
      {% csrf_token %}

      <div style="margin-bottom: 1.5rem;">
        <label for="id_email">Correo electrónico</label>
        <input type="email" name="email" id="id_email" autofocus
               autocomplete="email" required maxlength="254">
        {% if form.email.errors %}
        <div class="alert alert-error" style="margin-top: 0.5rem;">
          {{ form.email.errors.0 }}
        </div>
        {% endif %}
      </div>

      <button type="submit" class="btn btn-primary" style="width: 100%;">
        Enviarme el link
      </button>
    </form>
  </div>

  <p style="text-align: center; font-size: 0.85rem; margin-top: 1rem;">
    <a href="{% url 'accounts:login' %}">Volver al inicio de sesión</a>
  </p>
</div>
{% endblock %}
```

`templates/registration/password_reset_done.html`:

```django
{% extends "base.html" %}

{% block title %}Revisá tu correo — {{ config_sitio.nombre_sitio }}{% endblock %}

{% block content %}
<div class="container" style="max-width: 420px;">
  <div class="card" style="margin-top: 3rem;">
    <h2 style="margin-top: 0; margin-bottom: 0.75rem;">Revisá tu correo</h2>

    {# Redacción deliberada: "si esa dirección está registrada". Confirmar que #}
    {# lo está convertiría esta pantalla en un verificador de qué mails       #}
    {# existen en la plataforma.                                              #}
    <p style="margin-bottom: 1rem;">
      Si esa dirección está registrada en la plataforma, ya te llegó un mail
      con un link para elegir una contraseña nueva.
    </p>

    <p style="font-size: 0.9rem; color: #666; margin-bottom: 1rem;">
      El link vence en 24 horas y sirve una sola vez.
    </p>

    <p style="font-size: 0.9rem; color: #666; margin-bottom: 1.5rem;">
      Si no te llega en unos minutos, revisá la carpeta de spam. Si tampoco
      está ahí, escribile a tu docente: puede ser que tu cuenta tenga cargada
      otra dirección.
    </p>

    <a href="{% url 'accounts:login' %}" class="btn btn-primary"
       style="display: block; text-align: center;">Volver al inicio de sesión</a>
  </div>
</div>
{% endblock %}
```

`templates/registration/password_reset_confirm.html`:

```django
{% extends "base.html" %}

{% block title %}Elegir contraseña nueva — {{ config_sitio.nombre_sitio }}{% endblock %}

{% block content %}
<div class="container" style="max-width: 420px;">
  <div class="card" style="margin-top: 3rem;">
  {% if validlink %}
    <h2 style="margin-top: 0; margin-bottom: 1.5rem;">Elegí tu contraseña nueva</h2>

    {% if form.errors %}
    <div class="alert alert-error" style="margin-bottom: 1rem;">
      {% for error in form.non_field_errors %}<p style="margin: 0;">{{ error }}</p>{% endfor %}
      {% for field in form %}{% for error in field.errors %}<p style="margin: 0;">{{ error }}</p>{% endfor %}{% endfor %}
    </div>
    {% endif %}

    <form method="post" novalidate>
      {% csrf_token %}

      <div style="margin-bottom: 1rem;">
        <label for="id_new_password1">Contraseña nueva</label>
        <input type="password" name="new_password1" id="id_new_password1"
               autofocus autocomplete="new-password" required>
        <div style="font-size: 0.8rem; color: #666; margin-top: 0.4rem;">
          {{ form.new_password1.help_text|safe }}
        </div>
      </div>

      <div style="margin-bottom: 1.5rem;">
        <label for="id_new_password2">Repetir contraseña nueva</label>
        <input type="password" name="new_password2" id="id_new_password2"
               autocomplete="new-password" required>
      </div>

      <button type="submit" class="btn btn-primary" style="width: 100%;">Guardar</button>
    </form>
  {% else %}
    <h2 style="margin-top: 0; margin-bottom: 0.75rem;">Este link ya no sirve</h2>

    <p style="margin-bottom: 1.5rem;">
      Puede que haya vencido —los links duran 24 horas— o que ya lo hayas usado
      para cambiar la contraseña. Pedí uno nuevo y listo.
    </p>

    <a href="{% url 'accounts:password_reset' %}" class="btn btn-primary"
       style="display: block; text-align: center;">Pedir un link nuevo</a>
  {% endif %}
  </div>
</div>
{% endblock %}
```

`templates/registration/password_reset_complete.html`:

```django
{% extends "base.html" %}

{% block title %}Contraseña actualizada — {{ config_sitio.nombre_sitio }}{% endblock %}

{% block content %}
<div class="container" style="max-width: 420px;">
  <div class="card" style="margin-top: 3rem;">
    <h2 style="margin-top: 0; margin-bottom: 0.75rem;">Listo</h2>

    <p style="margin-bottom: 1.5rem;">
      Tu contraseña quedó actualizada. Ya podés entrar con ella.
    </p>

    <a href="{% url 'accounts:login' %}" class="btn btn-primary"
       style="display: block; text-align: center;">Iniciar sesión</a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Escribir los dos templates del mail**

`templates/registration/password_reset_subject.txt` (una sola línea; Django colapsa los saltos con `''.join(subject.splitlines())`):

```django
Recuperar tu contraseña de {{ nombre_sitio }}
```

`templates/registration/password_reset_email.html` — texto plano, sin variante HTML: mejor entregabilidad y no hay nada que maquetar. El `{% autoescape off %}` es necesario porque en un mail de texto plano un `&` no debe salir como `&amp;`:

```django
{% autoescape off %}Hola{% if user.first_name %} {{ user.first_name }}{% endif %}:

Alguien pidió recuperar la contraseña de la cuenta "{{ user.get_username }}" en {{ nombre_sitio }}.

Para elegir una contraseña nueva, entrá acá:

{{ protocol }}://{{ domain }}{% url 'accounts:password_reset_confirm' uidb64=uid token=token %}

Este link vence en 24 horas y sirve una sola vez: apenas lo uses, deja de funcionar.

Si no pediste esto, ignorá este mensaje. Tu contraseña sigue siendo la misma y nadie puede cambiarla sin abrir el link de arriba.
{% endautoescape %}
```

- [ ] **Step 7: Correr los tests y verificar que pasan**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordFlujoTests
```

Esperado: `Ran 5 tests ... OK`.

- [ ] **Step 8: Correr la suite entera de la app**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts
```

Esperado: `Ran 32 tests ... OK` (24 previos + 3 del Task 1 + 5 de éste).

- [ ] **Step 9: Commit**

```bash
git add accounts/views.py accounts/urls.py accounts/tests.py templates/registration/
git commit -m "feat(auth): flujo de recuperacion de contrasena por email"
```

---

### Task 3: Las dos garantías del link — un solo uso y 24 horas

Estos tests no agregan código: verifican que el Task 1 y el Task 2 juntos cumplen el requisito literal del pedido. Son la red que avisa si alguien toca el `PASSWORD_RESET_TIMEOUT` o cambia el generador de tokens.

**Files:**
- Test: `accounts/tests.py`

**Interfaces:**
- Consumes: `settings.PASSWORD_RESET_TIMEOUT` (Task 1); las rutas y el helper `_link_de_reset` (Task 2).
- Produces: nada que consuman otros tasks.

> **Cómo funciona el vencimiento.** `PasswordResetTokenGenerator._now()` devuelve un `datetime.now()` **naive**, y `check_token` compara `self._num_seconds(self._now()) - ts > settings.PASSWORD_RESET_TIMEOUT`. Para simular un link viejo se parchea `_now` **en el momento de fabricar el token**, no al validarlo. Por eso el `datetime` del patch es naive: si se le pasa uno con tzinfo, `_num_seconds` revienta restando naive y aware.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `accounts/tests.py`. Estos imports van arriba del módulo:

```python
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
```

```python
class RecuperarPasswordSeguridadDelLinkTests(TestCase):
    """Las dos propiedades que se pidieron explícitamente: un solo uso y 24 h."""

    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username='est_olvido',
            email='olvido@ejemplo.com',
            password='clave-vieja-123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        cache.clear()

    def _link_de_reset(self):
        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'olvido@ejemplo.com'},
        )
        self.assertTrue(mail.outbox, 'No llegó ningún mail.')
        for palabra in mail.outbox[-1].body.split():
            if '/accounts/reset/' in palabra:
                return palabra[palabra.index('/accounts/reset/'):]
        self.fail('El mail no contiene ningún link de reset.')

    def _link_con_antiguedad(self, horas):
        """Fabrica un link como si se hubiera pedido hace `horas` horas.

        Se parchea _now al fabricar el token, no al validarlo: el timestamp
        queda grabado adentro del token. El datetime es naive porque
        PasswordResetTokenGenerator._now() devuelve datetime.now() sin tzinfo,
        y _num_seconds() lo resta contra otro naive.
        """
        momento = datetime.now() - timedelta(hours=horas)
        with patch.object(default_token_generator, '_now', return_value=momento):
            token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        return reverse(
            'accounts:password_reset_confirm',
            kwargs={'uidb64': uid, 'token': token},
        )

    def test_el_link_no_sirve_dos_veces(self):
        link = self._link_de_reset()

        url_formulario = self.client.get(link)['Location']
        self.client.post(url_formulario, {
            'new_password1': 'clave-nueva-456',
            'new_password2': 'clave-nueva-456',
        })

        # Sesión limpia: que el segundo intento no se salve por el token que
        # PasswordResetConfirmView guarda en sesión.
        self.client.logout()

        response = self.client.get(link)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['validlink'])
        self.assertContains(response, 'Este link ya no sirve')

    def test_el_link_usado_no_revierte_la_clave_nueva(self):
        # Complementa al anterior: no alcanza con que la pantalla diga que no
        # sirve, la clave nueva tiene que seguir siendo la válida.
        link = self._link_de_reset()
        url_formulario = self.client.get(link)['Location']
        self.client.post(url_formulario, {
            'new_password1': 'clave-nueva-456',
            'new_password2': 'clave-nueva-456',
        })
        self.client.logout()

        self.client.get(link)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('clave-nueva-456'))

    def test_link_de_25_horas_ya_vencio(self):
        response = self.client.get(self._link_con_antiguedad(25))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['validlink'])

    def test_link_de_23_horas_todavia_sirve(self):
        # Sin este caso, el test de las 25 horas pasaría igual aunque el
        # vencimiento estuviera mal puesto en, digamos, una hora.
        response = self.client.get(self._link_con_antiguedad(23))

        self.assertEqual(response.status_code, 302)
        self.assertIn('set-password', response['Location'])
```

- [ ] **Step 2: Correr los tests y verificar que pasan a la primera**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordSeguridadDelLinkTests
```

Esperado: `Ran 4 tests ... OK`.

Acá **el test no arranca en rojo, y está bien**: no se está construyendo comportamiento nuevo sino fijando una propiedad que ya debe cumplirse. Si alguno falla, el problema está en el Task 1 o en el Task 2, no en este test.

- [ ] **Step 3: Verificar que el test de 25 horas realmente depende del setting**

Sin esta comprobación no hay evidencia de que el test de vencimiento mida algo. Cambiar temporalmente en `logica_ipc/settings.py`:

```python
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 3
```

Correr:

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordSeguridadDelLinkTests
```

Esperado: falla `test_link_de_25_horas_ya_vencio` (con 3 días, un link de 25 horas todavía sirve). **Revertir el valor a `60 * 60 * 24`** y volver a correr: `Ran 4 tests ... OK`.

- [ ] **Step 4: Commit**

```bash
git add accounts/tests.py
git commit -m "test(auth): el link de reset es de un solo uso y vence a las 24 h"
```

---

### Task 4: No pedirle dos veces la contraseña a quien recién la eligió

**Files:**
- Modify: `accounts/views.py`
- Modify: `accounts/urls.py` (la ruta `password_reset_confirm`)
- Test: `accounts/tests.py`

**Interfaces:**
- Consumes: las rutas del Task 2.
- Produces: `accounts.views.PasswordResetConfirmLimpiaFlagView`, subclase de `auth_views.PasswordResetConfirmView`.

El problema concreto: `EstudianteCreateForm.save()` deja `debe_cambiar_password = True`. Si ese estudiante nunca entró y recupera la contraseña por mail, `ForzarCambioPasswordMiddleware` lo va a mandar a `accounts:cambiar_password` a cambiar la contraseña que **acaba de elegir**. Limpiando el flag, el middleware pasa a su segundo check y lo lleva a consentimientos: el onboarding se completa igual, sin el paso redundante.

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `accounts/tests.py`:

```python
class RecuperarPasswordOnboardingTests(TestCase):
    """El reset tiene que encajar con el onboarding, no pelearse con él."""

    def setUp(self):
        self.User = get_user_model()
        # Tal cual lo deja EstudianteCreateForm: con el flag prendido y sin
        # consentimientos respondidos.
        self.user = self.User.objects.create_user(
            username='est_nuevo',
            email='nuevo@ejemplo.com',
            password='temporal-123',
            debe_cambiar_password=True,
        )
        cache.clear()

    def _link_de_reset(self):
        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'nuevo@ejemplo.com'},
        )
        self.assertTrue(mail.outbox, 'No llegó ningún mail.')
        for palabra in mail.outbox[-1].body.split():
            if '/accounts/reset/' in palabra:
                return palabra[palabra.index('/accounts/reset/'):]
        self.fail('El mail no contiene ningún link de reset.')

    def test_el_reset_limpia_debe_cambiar_password(self):
        link = self._link_de_reset()
        url_formulario = self.client.get(link)['Location']

        self.client.post(url_formulario, {
            'new_password1': 'clave-elegida-789',
            'new_password2': 'clave-elegida-789',
        })

        self.user.refresh_from_db()
        self.assertFalse(self.user.debe_cambiar_password)

    def test_despues_del_reset_el_middleware_lleva_a_consentimientos(self):
        # La otra mitad: limpiar el flag no debe saltear el onboarding, solo
        # el paso que ya cumplió. Los consentimientos siguen pendientes.
        link = self._link_de_reset()
        url_formulario = self.client.get(link)['Location']
        self.client.post(url_formulario, {
            'new_password1': 'clave-elegida-789',
            'new_password2': 'clave-elegida-789',
        })

        self.client.login(username='est_nuevo', password='clave-elegida-789')
        response = self.client.get(reverse('ejercicios:home'))

        self.assertRedirects(response, reverse('accounts:consentimientos'))

    def test_un_usuario_sin_el_flag_no_se_ve_afectado(self):
        otro = self.User.objects.create_user(
            username='est_veterano',
            email='veterano@ejemplo.com',
            password='clave-vieja-123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'veterano@ejemplo.com'},
        )
        link = None
        for palabra in mail.outbox[-1].body.split():
            if '/accounts/reset/' in palabra:
                link = palabra[palabra.index('/accounts/reset/'):]
        url_formulario = self.client.get(link)['Location']

        self.client.post(url_formulario, {
            'new_password1': 'clave-nueva-456',
            'new_password2': 'clave-nueva-456',
        })

        otro.refresh_from_db()
        self.assertFalse(otro.debe_cambiar_password)
        self.assertTrue(otro.check_password('clave-nueva-456'))
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordOnboardingTests
```

Esperado: falla `test_el_reset_limpia_debe_cambiar_password` con `True is not false`, y falla `test_despues_del_reset_el_middleware_lleva_a_consentimientos` porque el middleware redirige a `accounts:cambiar_password` en vez de a `accounts:consentimientos`.

- [ ] **Step 3: Escribir la vista**

En `accounts/views.py`, después de `PasswordResetSitioView`:

```python
class PasswordResetConfirmLimpiaFlagView(auth_views.PasswordResetConfirmView):
    """Al terminar el reset, baja ``debe_cambiar_password``.

    Un estudiante dado de alta por su docente arrastra el flag en True. Si
    recupera la contraseña por mail y el flag queda prendido,
    ForzarCambioPasswordMiddleware lo manda a cambiar la contraseña que acaba
    de elegir. Bajándolo, el middleware pasa a su segundo check y lo lleva a
    consentimientos: el onboarding sigue completo, sin el paso redundante.

    No se activa ``post_reset_login``: la persona termina en el login normal y
    entra con su contraseña nueva, como cualquiera.
    """

    def form_valid(self, form):
        response = super().form_valid(form)
        usuario = form.user
        if usuario.debe_cambiar_password:
            usuario.debe_cambiar_password = False
            usuario.save(update_fields=['debe_cambiar_password'])
        return response
```

- [ ] **Step 4: Cablearla en las URLs**

En `accounts/urls.py`, en la ruta `password_reset_confirm`, reemplazar `auth_views.PasswordResetConfirmView` por `views.PasswordResetConfirmLimpiaFlagView`:

```python
    path(
        'reset/<uidb64>/<token>/',
        views.PasswordResetConfirmLimpiaFlagView.as_view(
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordOnboardingTests
```

Esperado: `Ran 3 tests ... OK`.

- [ ] **Step 6: Commit**

```bash
git add accounts/views.py accounts/urls.py accounts/tests.py
git commit -m "fix(auth): el reset por mail limpia debe_cambiar_password"
```

---

### Task 5: Throttle del formulario público

`accounts:password_reset` es un endpoint público que dispara mails. Django no trae throttling. Sin límite, cualquiera puede usarlo para inundar la casilla de otra persona o para quemar la cuota del proveedor SMTP.

**Files:**
- Modify: `accounts/views.py`
- Test: `accounts/tests.py`

**Interfaces:**
- Consumes: `PasswordResetSitioView` (Task 2).
- Produces: en `accounts/views.py`, las constantes `LIMITE_RESET_POR_EMAIL = 5`, `LIMITE_RESET_POR_IP = 20`, `VENTANA_RESET_SEGUNDOS = 3600`, y los helpers `_ip_cliente(request) -> str` y `_excede_limite(clave: str, limite: int) -> bool`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `accounts/tests.py`:

```python
class RecuperarPasswordThrottleTests(TestCase):
    """El formulario es público y manda mails: hay que ponerle techo."""

    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username='est_olvido',
            email='olvido@ejemplo.com',
            password='clave-vieja-123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        # El contador vive en cache y el proceso de tests es uno solo.
        cache.clear()

    def test_los_primeros_cinco_pedidos_pasan(self):
        for _ in range(5):
            self.client.post(
                reverse('accounts:password_reset'),
                {'email': 'olvido@ejemplo.com'},
            )
        self.assertEqual(len(mail.outbox), 5)

    def test_el_sexto_pedido_no_manda_mail(self):
        for _ in range(5):
            self.client.post(
                reverse('accounts:password_reset'),
                {'email': 'olvido@ejemplo.com'},
            )

        response = self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'olvido@ejemplo.com'},
        )

        # Misma pantalla de siempre: devolver un error acá delataría que la
        # dirección existe y tiraría abajo el anti-enumeración.
        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 5)

    def test_el_limite_por_email_no_bloquea_a_otra_persona(self):
        self.User.objects.create_user(
            username='est_otro',
            email='otro@ejemplo.com',
            password='clave-vieja-123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        for _ in range(5):
            self.client.post(
                reverse('accounts:password_reset'),
                {'email': 'olvido@ejemplo.com'},
            )

        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'otro@ejemplo.com'},
        )

        # 5 del primero + 1 del segundo: el techo es por dirección, no global.
        self.assertEqual(len(mail.outbox), 6)
        self.assertEqual(mail.outbox[-1].to, ['otro@ejemplo.com'])

    def test_el_limite_por_ip_frena_el_sondeo_de_direcciones(self):
        # El techo por dirección no alcanza contra quien prueba direcciones
        # distintas: cada una estrena su propio contador. Para eso está el de
        # IP. Veinte pedidos con direcciones inventadas no mandan ningún mail
        # -no existen- pero igual consumen cupo, así que el pedido siguiente,
        # ya con una dirección que sí existe, tampoco sale.
        for i in range(20):
            self.client.post(
                reverse('accounts:password_reset'),
                {'email': f'sondeo{i}@ejemplo.com'},
            )
        self.assertEqual(len(mail.outbox), 0)

        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'olvido@ejemplo.com'},
        )

        self.assertEqual(len(mail.outbox), 0)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordThrottleTests
```

Esperado: fallan dos. `test_el_sexto_pedido_no_manda_mail` con `6 != 5`, y `test_el_limite_por_ip_frena_el_sondeo_de_direcciones` con `1 != 0`. Los otros dos pasan: todavía no hay techo que los frene, y eso es justamente lo que verifican.

- [ ] **Step 3: Escribir los helpers**

En `accounts/views.py`, agregar el import arriba:

```python
from django.core.cache import cache
```

Y en la línea 11, que hoy dice `from django.http import HttpResponse`, agregar el redirect:

```python
from django.http import HttpResponse, HttpResponseRedirect
```

Y antes de `PasswordResetSitioView`:

```python
# Techo del formulario público de recuperación de contraseña.
LIMITE_RESET_POR_EMAIL = 5
LIMITE_RESET_POR_IP = 20
VENTANA_RESET_SEGUNDOS = 60 * 60


def _ip_cliente(request):
    """IP de quien hace el pedido.

    En Railway la app corre detrás de un proxy, así que REMOTE_ADDR es el
    proxy y no sirve para distinguir clientes: se mira X-Forwarded-For y se
    toma el primer valor, que es el cliente original.
    """
    reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if reenviada:
        return reenviada.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _excede_limite(clave, limite):
    """Suma uno al contador de `clave` y dice si se pasó de `limite`.

    El par add+incr es el patrón que documenta Django para contadores en
    cache: `add` solo escribe si la clave no existía, así que la ventana de
    una hora se fija en el primer pedido y no se renueva con cada uno. El
    except cubre el caso en que la clave venza justo entre las dos llamadas.
    """
    cache_key = f'reset_pw:{clave}'
    cache.add(cache_key, 0, VENTANA_RESET_SEGUNDOS)
    try:
        contador = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, VENTANA_RESET_SEGUNDOS)
        contador = 1
    return contador > limite
```

- [ ] **Step 4: Agregar el throttle a la vista**

Reemplazar el `form_valid` de `PasswordResetSitioView` por:

```python
    def form_valid(self, form):
        email = form.cleaned_data['email'].strip().lower()

        # Los dos contadores se evalúan siempre, sin cortocircuito: si se
        # usara `or`, un pedido frenado por el límite de email no sumaría al
        # de IP y quien sondea direcciones distintas nunca tocaría ese techo.
        excede_email = _excede_limite(f'email:{email}', LIMITE_RESET_POR_EMAIL)
        excede_ip = _excede_limite(
            f'ip:{_ip_cliente(self.request)}', LIMITE_RESET_POR_IP
        )

        if excede_email or excede_ip:
            # Se corta el envío pero se devuelve la pantalla de siempre.
            # Un error acá diría "esta dirección existe y ya pidió cinco".
            return HttpResponseRedirect(self.get_success_url())

        self.extra_email_context = {
            'nombre_sitio': ConfigSitio.get().nombre_sitio,
        }
        return super().form_valid(form)
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordThrottleTests
```

Esperado: `Ran 4 tests ... OK`.

- [ ] **Step 6: Verificar que no se rompió el flujo de los tasks anteriores**

El `cache.clear()` de los `setUp` es lo que evita que el contador se filtre entre tests. Comprobarlo:

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts
```

Esperado: `Ran 43 tests ... OK`. Si algún test de los tasks 2–4 falla ahora por falta de mail, le falta `cache.clear()` en su `setUp`.

- [ ] **Step 7: Commit**

```bash
git add accounts/views.py accounts/tests.py
git commit -m "feat(auth): throttle del formulario publico de recuperacion"
```

---

### Task 6: La puerta de entrada

De nada sirve el flujo si nadie lo encuentra. El link va en el login, que es donde alguien descubre que no se acuerda la contraseña.

**Files:**
- Modify: `templates/registration/login.html`
- Modify: `templates/registration/acceso_comision.html`
- Test: `accounts/tests.py`

**Interfaces:**
- Consumes: la ruta `accounts:password_reset` (Task 2).
- Produces: nada.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `accounts/tests.py`:

```python
class RecuperarPasswordEntradaTests(TestCase):
    """Si el link no está donde la persona se da cuenta del problema, no existe."""

    def test_el_login_ofrece_recuperar_la_contrasena(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertContains(response, reverse('accounts:password_reset'))

    def test_la_puerta_de_comision_tambien_lo_ofrece(self):
        from cursos.models import Comision
        comision = Comision.objects.create(nombre='IPC comisión de prueba')

        response = self.client.get(
            reverse('accounts:acceso_comision', args=[comision.id])
        )

        self.assertContains(response, reverse('accounts:password_reset'))
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordEntradaTests
```

Esperado: los 2 fallan con `Couldn't find '/accounts/password_reset/' in response`.

- [ ] **Step 3: Agregar el link al login**

En `templates/registration/login.html`, reemplazar el párrafo final:

```django
  <p style="text-align: center; font-size: 0.85rem; color: #666; margin-top: 1rem;">
    Si no tenés cuenta, ingresá desde el link de tu comisión para registrarte.
  </p>
```

por:

```django
  <p style="text-align: center; font-size: 0.85rem; margin-top: 1rem;">
    <a href="{% url 'accounts:password_reset' %}">¿Olvidaste tu contraseña?</a>
  </p>

  <p style="text-align: center; font-size: 0.85rem; color: #666; margin-top: 0.5rem;">
    Si no tenés cuenta, ingresá desde el link de tu comisión para registrarte.
  </p>
```

- [ ] **Step 4: Agregar el link a la puerta de comisión**

Es la otra pantalla donde alguien llega sin poder entrar: le pasaron el link de la comisión, ya tiene cuenta y no se acuerda la clave. En `templates/registration/acceso_comision.html`, dentro del `<div>` que contiene el botón *Ya tengo cuenta*, agregar el `<a>` de recuperación después del que ya está:

```django
    <div style="display:flex; gap:0.6rem; flex-wrap:wrap; margin-bottom:1.1rem;">
      <a class="btn btn-secondary" href="{{ login_url }}">Ya tengo cuenta · Iniciar sesión</a>
      <a class="btn btn-secondary" href="{% url 'accounts:password_reset' %}">Olvidé mi contraseña</a>
    </div>
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test accounts.tests.RecuperarPasswordEntradaTests
```

Esperado: `Ran 2 tests ... OK`.

- [ ] **Step 6: Commit**

```bash
git add templates/registration/login.html templates/registration/acceso_comision.html accounts/tests.py
git commit -m "feat(auth): link de recuperacion en login y puerta de comision"
```

---

### Task 7: Verificación end-to-end y documentación

**Files:**
- Modify: `AGENTS.md` (sección *Estado funcional de referencia*)
- Modify: `MEMORY.md` (entrada de bitácora ya abierta el 2026-08-26)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: nada.

- [ ] **Step 1: Correr la suite completa del proyecto**

No alcanza con `accounts`: se tocaron `settings.py` y `templates/`, que usan todas las apps.

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test
```

Esperado: `OK`, con 21 tests más que el baseline previo a esta rama (24 → 45 en `accounts`). Cualquier fallo en otra app es una regresión de este trabajo, no un test preexistente roto: la suite estaba en verde al empezar.

- [ ] **Step 2: Confirmar que no se coló ninguna migración ni dependencia**

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py makemigrations --check --dry-run
git diff master --stat -- requirements.txt
```

Esperado: `No changes detected`, y el `git diff` vacío.

- [ ] **Step 3: Probar el flujo a mano, con el mail saliendo por consola**

Sin `EMAIL_HOST` en el entorno, el mail se imprime en la terminal donde corre el server. Levantarlo:

```bash
SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py runserver
```

Recorrer, y **mirar la pantalla, no solo el código**:

1. `http://localhost:8000/accounts/login/` → tiene que verse el link *¿Olvidaste tu contraseña?*.
2. Clickearlo, poner el mail de un usuario que exista en la base local.
3. En la terminal aparece el mail. Verificar que el asunto trae el nombre del sitio (no un host tipo `localhost:8000`) y que el cuerpo dice *24 horas* y *una sola vez*.
4. Copiar el link del mail y abrirlo: tiene que redirigir a una URL terminada en `/set-password/` — **el token no debe quedar en la barra de direcciones**.
5. Elegir una contraseña nueva y entrar con ella.
6. Volver a abrir el link del paso 4: tiene que aparecer *Este link ya no sirve*.
7. Poner un mail inexistente en el formulario: tiene que mostrar la **misma** pantalla que en el paso 3.

Si algo de esto no se cumple, es un bug, aunque los 45 tests estén en verde.

- [ ] **Step 3 bis: Verificar entrega real antes de anunciar la feature**

Los 45 tests corren contra el backend `locmem`: prueban que la app **arma y
entrega el mail al backend**, no que el mail **llegue**. Son dos cosas
distintas y la segunda no se puede testear desde la suite.

Este paso solo aplica cuando ya haya credenciales SMTP cargadas en Railway. Si
todavía no las hay, saltearlo y **no anunciar la feature a los estudiantes**:
con el backend de consola, quien pida recuperar su contraseña ve la pantalla
de "revisá tu correo" y no le llega nada nunca.

1. Cargar en Railway `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
   `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` y `DEFAULT_FROM_EMAIL`.
2. Pedir un reset desde el sitio en producción, usando una cuenta de prueba
   propia, **con casilla en Gmail**: es donde está la mayoría de los
   estudiantes y el receptor más estricto.
3. Mirar **dónde cayó**. Si cayó en spam, la feature no está lista, por más
   que el mail haya salido.
4. Repetir con una casilla de otro proveedor (Outlook/Hotmail o la
   institucional), que suelen tener reglas distintas.

Si `DEFAULT_FROM_EMAIL` es una dirección `@gmail.com` verificada como
remitente suelto, esperar que una parte caiga en spam: SPF y DKIM no pueden
alinear para gmail.com. Es la razón por la que conviene un dominio propio. La
mitigación mientras tanto ya está en la pantalla —`password_reset_done.html`
dice "revisá la carpeta de spam"— y hay que sostenerla también en la
comunicación a la cátedra.

- [ ] **Step 4: Actualizar `AGENTS.md`**

En *Estado funcional de referencia*, debajo del bullet que arranca con `- Onboarding con cambio obligatorio de contraseña`, agregar:

```markdown
- **Recuperación de contraseña por email** (`django.contrib.auth`, sin dependencias nuevas): link firmado, de un solo uso, que vence a las 24 h (`PASSWORD_RESET_TIMEOUT`). Backend SMTP por variables de entorno; **sin `EMAIL_HOST` los mails salen por consola y nadie recibe nada**, así que la feature no debe anunciarse hasta tener credenciales cargadas y entrega verificada. El formulario público tiene techo de 5 pedidos por dirección y 20 por IP cada hora, y nunca revela si una dirección está registrada.
```

- [ ] **Step 5: Cerrar la entrada de bitácora en `MEMORY.md`**

En la entrada `2026-08-26 (ART) — agente:claude-opus-5 — rama:claude/recuperar-password`, reemplazar las tres últimas líneas (`- Cambios: por ahora solo el spec...`, `- Tests/checks: pendiente.`, `- Commit: pendiente.`) por el estado real: archivos tocados, resultado de la suite completa, cantidad de commits y estado del PR.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md MEMORY.md
git commit -m "docs: registra la recuperacion de contrasena por email"
```

---

## Cobertura del spec

| Requisito del spec | Task |
|---|---|
| Backend SMTP por env vars, consola en local | 1 |
| `PASSWORD_RESET_TIMEOUT` = 24 h · `EMAIL_TIMEOUT` | 1 |
| 7 variables documentadas en `.env.example` y `README.md` | 1 |
| Las 4 rutas con `success_url` namespaceado | 2 |
| `nombre_sitio` en el mail (los context processors no corren ahí) | 2 |
| 4 templates de pantalla + asunto + cuerpo del mail | 2 |
| Mail en texto plano que avisa vencimiento y uso único | 2 |
| Anti-enumeración ante mail desconocido | 2 |
| Link vencido / `uidb64` corrupto → pantalla de link inválido | 2, 3 |
| Un solo uso | 3 |
| Vence a las 24 h (y sirve a las 23) | 3 |
| Limpiar `debe_cambiar_password` sin saltear el onboarding | 4 |
| Throttle 5/email y 20/IP por hora, sin revelar nada | 5 |
| Link de entrada en el login | 6 |
| `AGENTS.md` + bitácora en `MEMORY.md` | 7 |
| Sin migraciones, sin dependencias nuevas | 1, 7 |

Fuera de alcance por decisión del spec, y por eso sin task: verificación de email al registrarse, `PasswordChangeView`, `unique=True` en `email`, cola de mails.
