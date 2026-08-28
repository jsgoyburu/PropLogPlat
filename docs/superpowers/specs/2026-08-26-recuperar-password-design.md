# Autorecuperación de contraseña por email

Fecha: 2026-08-26

## Objetivo

Que un estudiante que olvidó su contraseña pueda recuperarla solo, sin
depender de que un docente se la resetee a mano.

El pedido, literal: un mail a la dirección registrada, con un link seguro,
de un solo uso, que venza a las 24 horas.

## Estado actual

No hay ninguna forma de recuperar una contraseña. Las tres vías existentes
requieren a alguien más:

- el docente edita al estudiante desde el panel (`docentes/views.py`),
- un admin usa `manage.py changepassword`,
- el estudiante se crea otra cuenta, que es lo que efectivamente pasa y
  duplica su historial de intentos.

El proyecto **no tiene ninguna configuración de email**. No hay
`EMAIL_BACKEND`, ni `DEFAULT_FROM_EMAIL`, ni ningún `send_mail` en el código.
Esto se construye desde cero.

Todas las vías de alta de estudiante exigen mail, así que el dato está:

| Alta | Formulario | Mail |
|---|---|---|
| Auto-registro por link de comisión | `RegistroEstudianteComisionForm` | obligatorio y único (`clean_email`) |
| Alta individual por docente | `EstudianteCreateForm` | obligatorio y único |
| Importación masiva desde Excel | `EstudianteCreateForm` (columna B) | obligatorio y único |

La unicidad se valida en el formulario, no en la base — `AbstractUser.email`
no tiene `unique=True`. No se agrega el constraint acá: hay cuentas viejas
que podrían violarlo y limpiarlas es otro trabajo. No hace falta, además:
`PasswordResetForm` le manda a *todos* los usuarios que coincidan.

## Investigación: qué biblioteca usar

Ninguna. Django trae exactamente esto en `django.contrib.auth`. Verificado
contra la 6.0.2 instalada en el venv, leyendo el fuente.

### Cómo cumple los tres requisitos

**Link seguro.** `PasswordResetTokenGenerator` produce un HMAC salteado con
`SECRET_KEY` sobre `f"{user.pk}{user.password}{login_timestamp}{timestamp}{email}"`.
No es un identificador guardado en una tabla: es una firma. Sin la
`SECRET_KEY` no se puede fabricar ni adivinar, y como el hash de la
contraseña entra en la firma, el token tampoco sirve para atacar la
contraseña.

**Un solo uso.** No hay marca de "usado" en ninguna parte, y no hace falta:
al resetear cambia `user.password` (aun eligiendo la misma clave, porque el
salt es nuevo), y eso invalida la firma. Además `last_login` también está en
la entrada del hash, así que el primer login posterior lo mata de nuevo.
Es revocación por construcción, sin estado que mantener.

**Vencimiento.** `check_token` termina con:

```python
if (self._num_seconds(self._now()) - ts) > settings.PASSWORD_RESET_TIMEOUT:
    return False
```

El default de `PASSWORD_RESET_TIMEOUT` es `259200` (3 días). Ponerlo en
`86400` da 24 horas exactas. Es un setting, nada más.

### De yapa

- `PasswordResetView` muestra siempre la misma pantalla, exista o no la
  cuenta: no se puede usar el formulario para enumerar mails registrados.
- `PasswordResetConfirmView` no deja el token en la URL mientras se escribe
  la contraseña. Lo guarda en sesión y redirige a `.../set-password/`, para
  que no se filtre por el header `Referer`.
- `PasswordResetForm.get_users` ya excluye `is_active=False` y cuentas con
  contraseña inusable.

### Alternativas descartadas

| Opción | Por qué no |
|---|---|
| **django-allauth** | Suite completa de autenticación. Obligaría a reescribir `LoginConPrimerAccesoView`, `acceso_comision` y `ForzarCambioPasswordMiddleware`. Riesgo desproporcionado para algo ya resuelto en el core. |
| **djoser / dj-rest-auth** | Orientadas a API para SPA con DRF. Acá el flujo es server-rendered con templates. |
| **django-rest-passwordreset** | Guarda tokens en tabla propia. Más estado que mantener y peor seguridad que una firma HMAC. |

Sumar cualquiera de las tres significaría además tocar `requirements.txt`,
que está pinneado a propósito desde que el rebuild del 2026-08-07 tiró abajo
los dos servicios.

## Diseño

Sin modelos nuevos, **sin migraciones**.

### 1. Configuración — `logica_ipc/settings.py`

Bloque nuevo, entre *Cache* y *Modelo de usuario personalizado*:

```python
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24   # 24 h
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'IPC-Lógica <no-reply@localhost>')
```

El backend se elige por presencia de `EMAIL_HOST`:

- **con `EMAIL_HOST`** → `smtp.EmailBackend`, tomando `EMAIL_PORT` (default
  587), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` (default
  True) y `EMAIL_USE_SSL` del entorno.
- **sin `EMAIL_HOST`** → `console.EmailBackend`. En desarrollo el mail se
  imprime en la terminal, con el link clickeable, y no hacen falta
  credenciales para probar el flujo entero.

SMTP genérico y no la API HTTP de un proveedor: entran por la misma puerta
Gmail (app password), Resend, SendGrid, Brevo y Mailgun. Cambiar de
proveedor es cambiar variables de entorno, no código, y no suma
dependencias.

`EMAIL_TIMEOUT = 10` no es decorativo: sin él, un SMTP que no responde
bloquea un worker de gunicorn hasta el timeout del socket del sistema.

### 2. URLs — `accounts/urls.py`

```
password_reset/                    → accounts:password_reset
password_reset/enviado/            → accounts:password_reset_done
reset/<uidb64>/<token>/            → accounts:password_reset_confirm
reset/completo/                    → accounts:password_reset_complete
```

**Cuidado con el namespace.** `accounts/urls.py` declara `app_name = 'accounts'`,
pero las vistas de Django resuelven sus destinos sin namespace:

```python
class PasswordResetView(...):
    success_url = reverse_lazy("password_reset_done")

class PasswordResetConfirmView(...):
    success_url = reverse_lazy("password_reset_complete")
```

Hay que pasar `success_url=reverse_lazy('accounts:...')` en ambas. Si no,
el flujo explota con `NoReverseMatch` recién al enviar el formulario, no al
arrancar. El template del mail tiene el mismo problema con su `{% url %}`.

### 3. Dos subclases — `accounts/views.py`

**`PasswordResetConThrottleView(PasswordResetView)`** — Django no trae
throttling y este es un endpoint público que manda mails. Contador en cache
(Redis ya está configurado en `CACHES`; en local cae a LocMemCache y anda
igual):

- 5 pedidos por dirección de mail por hora,
- 20 pedidos por IP por hora.

Al excederse **se muestra la misma pantalla de éxito de siempre** pero no se
manda nada. Devolver un error acá delataría que la dirección existe y
tiraría abajo el anti-enumeración de Django.

**`PasswordResetConfirmLimpiaFlagView(PasswordResetConfirmView)`** — un
`form_valid` que llama a `super()` y después, si el usuario tenía
`debe_cambiar_password=True`, lo pone en `False` con
`save(update_fields=[...])`.

Sin esto, un estudiante creado por su docente que nunca entró y recupera la
clave por mail sería redirigido por `ForzarCambioPasswordMiddleware` a
`cambiar_password` para que cambie la contraseña que **acaba de elegir**.
Limpiando el flag, el middleware pasa a su segundo check y lo manda a
consentimientos, y de ahí a la encuesta: el onboarding se completa igual,
sin el paso redundante.

No se activa `post_reset_login` (default `False`): el usuario termina en el
login normal y entra con su contraseña nueva. Que el middleware lo encamine
desde ahí, como a cualquier otro.

### 4. Templates — `templates/registration/`

Seis archivos. Los cuatro de pantalla siguen el estilo de `login.html`:
`container` de 420px, `card`, `btn btn-primary`, `alert alert-error`.

| Archivo | Contenido |
|---|---|
| `password_reset_form.html` | pedir la dirección de mail |
| `password_reset_done.html` | "si esa dirección está registrada, te llegó un mail" |
| `password_reset_confirm.html` | nueva contraseña, o el aviso de link inválido |
| `password_reset_complete.html` | listo, con link al login |
| `password_reset_email.html` | cuerpo del mail, texto plano |
| `password_reset_subject.txt` | asunto, una línea |

Los seis existen ya en Django (`contrib/admin/templates/registration/` y
`contrib/auth/templates/registration/`), en inglés y con estética de admin.
Como `TEMPLATES.DIRS` incluye `BASE_DIR / 'templates'` y se resuelve antes
que `APP_DIRS`, estos los tapan sin configuración extra.

El cuerpo va en texto plano, sin variante HTML: mejor entregabilidad, menos
chance de caer en spam, y no hay nada que maquetar. Dice explícitamente que
el link vence en 24 horas y que sirve una sola vez.

### 5. Entrada — `templates/registration/login.html`

Link "¿Olvidaste tu contraseña?" debajo del botón *Entrar*.

## Manejo de errores

| Situación | Qué ve el usuario |
|---|---|
| Link vencido (>24 h) o ya usado | `validlink=False` → "este link ya no sirve", con botón para pedir otro |
| `uidb64` corrupto o usuario borrado | mismo caso: `get_user` devuelve `None` |
| Mail no registrado, o cuenta sin mail | pantalla idéntica al caso exitoso |
| Cuenta con `is_active=False` | idem: `get_users` la filtra en silencio |
| Excedió el throttle | idem |
| SMTP caído | 500 en el POST. Aceptado: reintentar es del usuario, y una cola de mails es otro proyecto |

En los cuatro casos silenciosos, `password_reset_done.html` cierra con "si
no te llega en unos minutos, revisá spam o escribile a tu docente" — que es
la salida real para quien no tiene mail cargado, sin revelarle a un tercero
qué direcciones están registradas.

## Tests — `accounts/tests.py`

Django reemplaza el backend de mail por `locmem` durante los tests, así que
`mail.outbox` sirve sin mockear nada.

| # | Caso | Qué prueba |
|---|---|---|
| 1 | Pedido con mail válido | manda 1 mail y el link está en el cuerpo |
| 2 | Pedido con mail inexistente | 200, `outbox` vacío (anti-enumeración) |
| 3 | Flujo completo | el token cambia la clave y permite loguearse |
| 4 | **Segundo uso del token** | el link no sirve dos veces |
| 5 | **Token de más de 24 h** | vence (mockeando `_now` del generador) |
| 6 | Token de 23 h | todavía sirve — que 5 no pase por un off-by-one |
| 7 | `PASSWORD_RESET_TIMEOUT == 86400` | el valor no se cambia sin querer |
| 8 | Reset con `debe_cambiar_password=True` | el flag queda en `False` |
| 9 | Sexto pedido en una hora | no manda mail, devuelve 200 |
| 10 | Login | el link "¿Olvidaste tu contraseña?" está |

Los casos 4, 5 y 6 son el requisito literal del pedido. El 8 cuida el
onboarding. El resto cuida que no se rompa nada de lo que ya anda.

Para crear usuarios se sigue lo que ya hace `accounts/tests.py`:
`User.objects.create_user(...)` pasando `consentimiento_pedagogico=True`,
`consentimiento_investigacion=True` y `encuesta_completada=True`, para no
chocar con `ForzarCambioPasswordMiddleware` en los casos que hacen login.
(El helper `_u` que usan `docentes/` y `ejercicios/` no existe en esta app y
no se importa desde otra: los módulos de tests acá son independientes.)

El caso 8 es la excepción deliberada: ahí el usuario se crea con
`debe_cambiar_password=True` justamente para verificar que el reset lo baja.

## Nota de seguridad: la dirección guardada pasa a ser una credencial

`PasswordResetForm.save()` hace:

```python
for user in self.get_users(email):
    user_email = getattr(user, email_field_name)
    ...
    self.send_mail(..., user_email, ...)
```

El mail sale **siempre a la dirección guardada en la cuenta**. De ahí se
sigue lo único que importa: *quien controla la casilla controla la cuenta*.

Conviene descartar primero el caso que parece el peligroso y no lo es. Si
alguien se registra usando el mail de otra persona, el link de reset le
llega a **la otra persona**, no al que se registró. El registrante no recibe
nada y no gana nada: la cuenta que creó ya era suya. Es una molestia para el
dueño de la casilla, no una toma de control.

El riesgo va en la dirección contraria, y aparece cuando una cuenta tiene
guardada una dirección que no es de su dueño:

- Un docente importa el Excel con un error en la columna B y la cuenta de A
  queda con el mail de B. B pide recuperar y recibe un link válido para la
  cuenta de A.
- La unicidad de mail se valida en los formularios, no en la base. Una
  cuenta creada por `createsuperuser`, por el admin o por un import viejo
  puede repetir una dirección. Como el envío recorre *todos* los usuarios
  que coinciden, un solo pedido manda a esa casilla un link por cada cuenta.

Lo que cambia con esta feature no es que existan mails mal cargados —eso ya
pasaba—, sino que dejan de ser inocuos. Hasta hoy una dirección equivocada
no hacía nada porque el sistema nunca mandaba mails. A partir de ahora es
una vía de acceso a la cuenta.

La verificación de email al registrarse es lo que cierra esto, y queda fuera
de alcance porque toca las tres vías de alta. **Mientras tanto la mitigación
es operativa**: revisar la columna de mails antes de importar, y tratar un
pedido de corrección de mail como lo que ahora es —un cambio de credencial—
y no como un dato de contacto.

### Calibración de severidad

Esto no es una urgencia, y la razón es pedagógica antes que técnica. La
política del proyecto es explícita en que **resolver ejercicios no afecta la
evaluación ni la calificación** (principio 2: la automatización es formativa,
no acreditadora). Tomar la cuenta de otro no permite subirle ni bajarle la
nota a nadie, porque no hay nota que tocar. El incentivo para hacerlo es
prácticamente nulo.

La salvedad, para que la decisión quede completa: la cuenta sí guarda datos
personales de la `EncuestaEstudiante` —facultad, carrera, geografía,
situación personal, acceso a internet y dispositivos— y los consentimientos
firmados. El daño posible es de privacidad, no de acreditación. Sigue siendo
menor y sigue justificando no frenar esta feature, pero cambiaría si en algún
momento la plataforma pasara a informar calificaciones.

## Fuera de alcance

- **Verificación de email al registrarse.** Hoy nadie confirma que la
  dirección sea suya. Ver más abajo por qué importa y por qué igual queda
  afuera.
- **`PasswordChangeView`** para cambiar la clave estando logueado. No se
  pidió.
- **`unique=True` en `email`** a nivel base de datos. Requiere migración y
  auditar cuentas existentes.
- **Cola de mails / reintentos.** El envío es sincrónico dentro del request.

## Variables de entorno nuevas

A documentar en `README.md`:

| Variable | Default | Nota |
|---|---|---|
| `EMAIL_HOST` | — | Sin ella, backend de consola |
| `EMAIL_PORT` | `587` | |
| `EMAIL_HOST_USER` | `''` | |
| `EMAIL_HOST_PASSWORD` | `''` | Secreto |
| `EMAIL_USE_TLS` | `True` | |
| `EMAIL_USE_SSL` | `False` | Mutuamente excluyente con TLS |
| `DEFAULT_FROM_EMAIL` | `IPC-Lógica <no-reply@localhost>` | Remitente visible |
