import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LoginView
from django.contrib.auth.forms import SetPasswordForm
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.facultades import get_facultades_carreras_por_clave

from .forms import (
    ConsentimientosForm,
    EncuestaForm,
    InstalacionInicialForm,
    PerfilForm,
    RegistroEstudianteComisionForm,
)
from .models import ConfigSitio, EncuestaEstudiante
from cursos.models import Comision, Inscripcion

User = get_user_model()


def healthz(request):
    """Health check sin datos sensibles para proveedores de despliegue."""
    return HttpResponse('ok', content_type='text/plain')


def instalacion_inicial(request):
    """Configura una instancia nueva y se cierra de forma permanente."""
    from django.conf import settings

    config = ConfigSitio.get()
    if config.instalacion_completada or User.objects.filter(is_superuser=True).exists():
        if not config.instalacion_completada:
            config.instalacion_completada = True
            config.save(update_fields=['instalacion_completada'])
        return redirect('accounts:login')

    sin_token_produccion = not settings.DEBUG and not settings.SETUP_TOKEN
    form = InstalacionInicialForm(request.POST or None)
    if request.method == 'POST' and not sin_token_produccion and form.is_valid():
        try:
            with transaction.atomic():
                # El bloqueo del singleton evita dos instalaciones simultáneas.
                config = ConfigSitio.objects.select_for_update().get(pk=1)
                if config.instalacion_completada or User.objects.filter(is_superuser=True).exists():
                    return redirect('accounts:login')
                admin_user = User.objects.create_superuser(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password1'],
                    es_docente=True,
                    debe_cambiar_password=False,
                    consentimiento_pedagogico=False,
                    consentimiento_investigacion=False,
                    consentimiento_contacto_seguimiento=False,
                    encuesta_completada=True,
                )
                config.nombre_sitio = form.cleaned_data['nombre_sitio']
                config.idioma_predeterminado = form.cleaned_data['idioma_predeterminado']
                config.contacto_privacidad = form.cleaned_data['contacto_privacidad']
                config.instalacion_completada = True
                config.save(update_fields=[
                    'nombre_sitio', 'idioma_predeterminado', 'contacto_privacidad',
                    'instalacion_completada',
                ])
        except IntegrityError:
            form.add_error(None, 'La instalación ya fue completada en otra sesión.')
        else:
            login(request, admin_user)
            messages.success(request, 'Instalación completada. Ya podés configurar y usar el sitio.')
            return redirect('admin:index')

    return render(request, 'registration/instalacion_inicial.html', {
        'form': form,
        'sin_token_produccion': sin_token_produccion,
    }, status=503 if sin_token_produccion else 200)


def acceso_comision(request, comision_id):
    """Puerta de acceso pública por comisión para login o auto-registro."""
    comision = get_object_or_404(Comision, pk=comision_id)

    from cursos.cohortes import cohorte_activa
    cohorte = cohorte_activa()

    # Ventana entre cuatrimestres: el constraint garantiza a lo sumo una
    # cohorte activa, no al menos una. Es un endpoint público sin autenticar,
    # así que acá no puede quedar un 500 crudo por el NOT NULL de Inscripcion.
    mensaje_sin_cohorte = (
        'En este momento no hay un cuatrimestre activo, así que no es '
        'posible inscribirse. Volvé a intentarlo más adelante o contactá '
        'a tu docente.'
    )

    if request.user.is_authenticated:
        user = request.user
        if user.is_staff or user.es_docente:
            return redirect('docentes:comision_detail', comision_id=comision.id)

        # La cohorte es la camada de pertenencia, no el período del
        # calendario: si el estudiante ya tiene una inscripción en esta
        # comisión (de la cohorte que sea), no se crea una nueva -eso lo
        # convertiría en recursante sin haberlo pedido-. Solo se exige
        # cohorte activa cuando hace falta crear la primera inscripción.
        ya_inscripto = Inscripcion.objects.filter(
            estudiante=user, comision=comision,
        ).exists()
        if not ya_inscripto:
            if cohorte is None:
                messages.error(request, mensaje_sin_cohorte)
                return redirect('ejercicios:home')

            Inscripcion.objects.get_or_create(
                estudiante=user, comision=comision, cohorte=cohorte,
            )
        return redirect('ejercicios:home')

    if cohorte is None:
        messages.error(request, mensaje_sin_cohorte)
        login_url = f"{reverse('accounts:login')}?next={request.path}"
        return render(request, 'registration/acceso_comision.html', {
            'comision': comision,
            'form': RegistroEstudianteComisionForm(),
            'login_url': login_url,
        })

    form = RegistroEstudianteComisionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        Inscripcion.objects.get_or_create(
            estudiante=user, comision=comision, cohorte=cohorte,
        )
        login(request, user)
        messages.success(request, f'¡Bienvenido/a! Ya quedaste inscripto/a en {comision.nombre}.')
        return redirect('ejercicios:home')

    login_url = f"{reverse('accounts:login')}?next={request.path}"
    return render(request, 'registration/acceso_comision.html', {
        'comision': comision,
        'form': form,
        'login_url': login_url,
    })




def favicon_view(request):
    """Sirve el favicon almacenado en la base de datos (base64 en TextField)."""
    import base64
    config = ConfigSitio.get()
    if config.favicon_data:
        ct = config.favicon_content_type or 'image/x-icon'
        try:
            data = base64.b64decode(config.favicon_data)
        except Exception:
            return HttpResponse(status=404)
        response = HttpResponse(data, content_type=ct)
        response['Cache-Control'] = 'public, max-age=3600'
        return response
    return HttpResponse(status=404)


class LoginConPrimerAccesoView(LoginView):
    """LoginView estándar. La detección de primer acceso se hace en el modelo."""
    pass


# Techo del formulario público de recuperación de contraseña.
LIMITE_RESET_POR_EMAIL = 5
LIMITE_RESET_POR_IP = 20
VENTANA_RESET_SEGUNDOS = 60 * 60


def _ip_cliente(request):
    """IP de quien hace el pedido, leída desde el proxy de confianza.

    X-Forwarded-For se lee DE DERECHA A IZQUIERDA. El header queda como
    `<lo que mandó el cliente>, <lo que vio el proxy 1>, ...`: cada proxy
    agrega al final la dirección que él mismo vio, así que lo de la izquierda
    lo escribió quien llama y no se puede creer.

    Tomar el primer valor -que es lo que uno escribe sin pensarlo- deja el
    techo por IP en la nada: alcanza con mandar el header a mano y cambiarlo en
    cada pedido para estrenar un contador nuevo cada vez. Con
    ``settings.TRUSTED_PROXY_COUNT`` proxies de confianza delante (en Railway,
    uno), el valor confiable es el que está esa cantidad de posiciones desde el
    final.

    Sin el header se cae a REMOTE_ADDR, que es lo correcto cuando no hay proxy
    (desarrollo local y tests).
    """
    reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
    cadena = [ip.strip() for ip in reenviada.split(',') if ip.strip()]
    if cadena:
        confiables = getattr(settings, 'TRUSTED_PROXY_COUNT', 1)
        return cadena[max(len(cadena) - confiables, 0)]
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


def _get_tipo_encuesta(user):
    """Devuelve el tipo de encuesta priorizando comisiones completas.

    Si el estudiante está en múltiples comisiones, se prioriza ``completa``
    para no perder campos de la encuesta extendida.
    """
    tipos = list(
        user.inscripciones.select_related('comision')
        .values_list('comision__tipo_encuesta', flat=True)
    )
    if 'completa' in tipos:
        return 'completa'
    if 'basica' in tipos:
        return 'basica'
    return 'basica'


def _guardar_consentimientos(user, form_data, tipo):
    """Aplica los tres consentimientos al usuario según tipo de encuesta.

    Reglas:
    - pedagogico=False → investigacion=False, contacto=False, encuesta_completada=True
    - tipo='basica' y pedagogico=True → investigacion=False, contacto=False
    - tipo='completa' y pedagogico=True → investigacion y contacto según respuesta
    """
    pedagogico = form_data.get('consentimiento_pedagogico') == 'true'
    user.consentimiento_pedagogico = pedagogico

    if not pedagogico:
        user.consentimiento_investigacion = False
        user.consentimiento_contacto_seguimiento = False
        user.encuesta_completada = True
    elif tipo == 'basica':
        user.consentimiento_investigacion = False
        user.consentimiento_contacto_seguimiento = False
    else:
        user.consentimiento_investigacion = (
            form_data.get('consentimiento_investigacion') == 'true'
        )
        user.consentimiento_contacto_seguimiento = (
            form_data.get('consentimiento_contacto_seguimiento') == 'true'
        )

    # Generar research_id al dar consentimiento de investigación; anular si lo revoca.
    if user.consentimiento_investigacion:
        if user.research_id is None:
            import uuid
            user.research_id = uuid.uuid4()
    else:
        user.research_id = None

    user.fecha_consentimiento = timezone.now()


def _crear_encuesta_estudiante(user, data, tipo):
    """Crea o actualiza EncuestaEstudiante a partir de cleaned_data de EncuestaForm."""
    def _bool(val):
        if val == 'true':
            return True
        if val == 'false':
            return False
        return None

    whatsapp_raw = str(data.get('whatsapp', '') or '').strip()
    whatsapp = int(whatsapp_raw) if whatsapp_raw.isdigit() else None

    defaults = {
        'dni': data.get('dni', ''),
        'whatsapp': whatsapp,
        'fecha_nacimiento': data.get('fecha_nacimiento') or None,
    }

    if tipo == 'completa':
        dispositivos = {
            'celular': data.get('dispositivo_celular') or None,
            'tablet': data.get('dispositivo_tablet') or None,
            'pc': data.get('dispositivo_pc') or None,
            'laptop': data.get('dispositivo_laptop') or None,
        }
        dispositivos = {k: v for k, v in dispositivos.items() if v} or None

        defaults.update({
            'facultad': data.get('facultad', ''),
            'carrera': data.get('carrera', ''),
            'origen_caba_gba': _bool(data.get('origen_caba_gba')),
            'vive_en': data.get('vive_en', ''),
            'mudado_con_familia': _bool(data.get('mudado_con_familia')),
            'mudado_para_trabajar_estudiar': _bool(data.get('mudado_para_trabajar_estudiar')),
            'tiempo_mudado': data.get('tiempo_mudado', ''),
            'desde_donde': data.get('desde_donde', ''),
            'provincia_origen': data.get('provincia_origen', ''),
            'pais_origen': data.get('pais_origen', ''),
            'necesita_adecuacion': _bool(data.get('necesita_adecuacion')),
            'tiene_cud': _bool(data.get('tiene_cud')),
            'con_quien_vive': data.get('con_quien_vive', ''),
            'tiempo_viaje_puan': data.get('tiempo_viaje_puan', ''),
            'situacion_laboral': data.get('situacion_laboral', ''),
            'dias_trabaja': data.get('dias_trabaja', ''),
            'acceso_internet': list(data.get('acceso_internet', [])) or None,
            'dispositivos': dispositivos,
            'tiempo_desde_secundaria': data.get('tiempo_desde_secundaria', ''),
            'tipo_escuela': data.get('tipo_escuela', ''),
            'estudios_superiores': data.get('estudios_superiores', ''),
            'carrera_uba_anterior': data.get('carrera_uba_anterior', ''),
            'termino_cbc_anterior': _bool(data.get('termino_cbc_anterior')),
            'se_recibio_uba': _bool(data.get('se_recibio_uba')),
            'tipo_inst_fuera_uba': data.get('tipo_inst_fuera_uba', ''),
            'carrera_fuera_uba': data.get('carrera_fuera_uba', ''),
            'se_recibio_fuera_uba': _bool(data.get('se_recibio_fuera_uba')),
            'hizo_uba_xxi': _bool(data.get('hizo_uba_xxi')),
            'tiempo_en_cbc': data.get('tiempo_en_cbc', ''),
            'interrupcion_cbc': data.get('interrupcion_cbc', ''),
            'ya_curso_ipc': _bool(data.get('ya_curso_ipc')),
            'motivo_no_termino_ipc': data.get('motivo_no_termino_ipc', ''),
            'materias_aprobadas': data.get('materias_aprobadas'),
            'acertijo_silogismo': data.get('acertijo_silogismo', ''),
            'acertijo_cirugia': data.get('acertijo_cirugia', ''),
            'acertijo_hilera': data.get('acertijo_hilera', ''),
            'articulo_risa': _bool(data.get('articulo_risa')),
            'que_es_ciencia': data.get('que_es_ciencia', ''),
        })

    encuesta_obj, _ = EncuestaEstudiante.objects.update_or_create(
        estudiante=user,
        defaults=defaults,
    )

    if tipo == 'completa' and encuesta_obj.acertijo_cirugia_correcto is None:
        cirugia_text = (encuesta_obj.acertijo_cirugia or '').strip()
        if cirugia_text:
            from ejercicios.gemini_hints import evaluar_cirugia_groq
            resultado = evaluar_cirugia_groq(cirugia_text)
            if resultado is not None:
                encuesta_obj.acertijo_cirugia_correcto = resultado
                encuesta_obj.save(update_fields=['acertijo_cirugia_correcto'])
        else:
            encuesta_obj.acertijo_cirugia_correcto = False
            encuesta_obj.save(update_fields=['acertijo_cirugia_correcto'])


# Campos que no pueden editarse una vez enviada la encuesta
_ENCUESTA_READONLY_FIELDS = {
    'acertijo_silogismo', 'acertijo_cirugia', 'acertijo_cirugia_no_se',
    'acertijo_hilera', 'articulo_risa', 'que_es_ciencia',
}


def _encuesta_to_initial(encuesta, user, tipo):
    """Convierte un EncuestaEstudiante al dict initial del EncuestaForm."""
    def _boolstr(val):
        if val is True:
            return 'true'
        if val is False:
            return 'false'
        return ''

    initial = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'dni': encuesta.dni,
        'whatsapp': str(encuesta.whatsapp) if encuesta.whatsapp else '',
        'fecha_nacimiento': encuesta.fecha_nacimiento,
    }

    if tipo == 'completa':
        dispositivos = encuesta.dispositivos or {}
        cirugia = encuesta.acertijo_cirugia or ''
        initial.update({
            'facultad': encuesta.facultad,
            'carrera': encuesta.carrera,
            'origen_caba_gba': _boolstr(encuesta.origen_caba_gba),
            'vive_en': encuesta.vive_en,
            'mudado_con_familia': _boolstr(encuesta.mudado_con_familia),
            'mudado_para_trabajar_estudiar': _boolstr(encuesta.mudado_para_trabajar_estudiar),
            'tiempo_mudado': encuesta.tiempo_mudado,
            'desde_donde': encuesta.desde_donde,
            'provincia_origen': encuesta.provincia_origen,
            'pais_origen': encuesta.pais_origen,
            'necesita_adecuacion': _boolstr(encuesta.necesita_adecuacion),
            'tiene_cud': _boolstr(encuesta.tiene_cud),
            'con_quien_vive': encuesta.con_quien_vive,
            'tiempo_viaje_puan': encuesta.tiempo_viaje_puan,
            'situacion_laboral': encuesta.situacion_laboral,
            'dias_trabaja': encuesta.dias_trabaja,
            'acceso_internet': list(encuesta.acceso_internet or []),
            'dispositivo_celular': dispositivos.get('celular', ''),
            'dispositivo_tablet': dispositivos.get('tablet', ''),
            'dispositivo_pc': dispositivos.get('pc', ''),
            'dispositivo_laptop': dispositivos.get('laptop', ''),
            'tiempo_desde_secundaria': encuesta.tiempo_desde_secundaria,
            'tipo_escuela': encuesta.tipo_escuela,
            'estudios_superiores': encuesta.estudios_superiores,
            'carrera_uba_anterior': encuesta.carrera_uba_anterior,
            'termino_cbc_anterior': _boolstr(encuesta.termino_cbc_anterior),
            'se_recibio_uba': _boolstr(encuesta.se_recibio_uba),
            'tipo_inst_fuera_uba': encuesta.tipo_inst_fuera_uba,
            'carrera_fuera_uba': encuesta.carrera_fuera_uba,
            'se_recibio_fuera_uba': _boolstr(encuesta.se_recibio_fuera_uba),
            'hizo_uba_xxi': _boolstr(encuesta.hizo_uba_xxi),
            'tiempo_en_cbc': encuesta.tiempo_en_cbc,
            'interrupcion_cbc': encuesta.interrupcion_cbc,
            'ya_curso_ipc': _boolstr(encuesta.ya_curso_ipc),
            'motivo_no_termino_ipc': encuesta.motivo_no_termino_ipc,
            'materias_aprobadas': encuesta.materias_aprobadas,
            'acertijo_silogismo': encuesta.acertijo_silogismo or '',
            'acertijo_cirugia_no_se': 'true' if cirugia == 'No sé' else '',
            'acertijo_cirugia': cirugia if cirugia != 'No sé' else '',
            'acertijo_hilera': encuesta.acertijo_hilera or '',
            'articulo_risa': _boolstr(encuesta.articulo_risa),
            'que_es_ciencia': encuesta.que_es_ciencia or '',
        })

    return initial


def cambiar_password_forzado(request):
    """Vista para el cambio de contraseña obligatorio en el primer ingreso.

    Combina el formulario de nueva contraseña con los consentimientos.
    Ambos formularios deben ser válidos para continuar.
    """
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    if not request.user.debe_cambiar_password:
        return redirect('ejercicios:home')

    tipo = _get_tipo_encuesta(request.user)

    if request.method == 'POST':
        form = SetPasswordForm(request.user, request.POST)
        consent_form = ConsentimientosForm(request.POST)
        if form.is_valid() and consent_form.is_valid():
            user = form.save()
            user.debe_cambiar_password = False
            _guardar_consentimientos(user, consent_form.cleaned_data, tipo)
            user.save(update_fields=[
                'debe_cambiar_password',
                'consentimiento_pedagogico',
                'consentimiento_investigacion',
                'consentimiento_contacto_seguimiento',
                'fecha_consentimiento',
                'encuesta_completada',
                'research_id',
            ])
            update_session_auth_hash(request, user)
            return redirect('ejercicios:home')
    else:
        form = SetPasswordForm(request.user)
        consent_form = ConsentimientosForm()

    return render(request, 'registration/cambiar_password.html', {
        'form': form,
        'consent_form': consent_form,
        'tipo': tipo,
    })


def dar_consentimiento(request):
    """Vista para registrar consentimientos de usuarios que ya cambiaron su password.

    Para usuarios preexistentes que completaron el primer login antes de que
    se implementara el sistema de consentimientos.
    """
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    user = request.user
    if (
        user.consentimiento_pedagogico is not None
        and user.consentimiento_investigacion is not None
    ):
        return redirect('ejercicios:home')

    tipo = _get_tipo_encuesta(user)

    if request.method == 'POST':
        consent_form = ConsentimientosForm(request.POST)
        if consent_form.is_valid():
            _guardar_consentimientos(user, consent_form.cleaned_data, tipo)
            user.save(update_fields=[
                'consentimiento_pedagogico',
                'consentimiento_investigacion',
                'consentimiento_contacto_seguimiento',
                'fecha_consentimiento',
                'encuesta_completada',
                'research_id',
            ])
            return redirect('ejercicios:home')
    else:
        consent_form = ConsentimientosForm()

    return render(request, 'registration/consentimientos.html', {
        'consent_form': consent_form,
        'tipo': tipo,
    })


@login_required
def encuesta_onboarding(request):
    """Vista de la encuesta socioeducativa de onboarding.

    Solo accesible para estudiantes con consentimiento pedagógico=True
    y encuesta_completada=False. El middleware garantiza la redirección.
    """
    user = request.user
    if user.es_docente or user.is_staff:
        return redirect('ejercicios:home')
    if user.encuesta_completada:
        return redirect('ejercicios:home')

    tipo = _get_tipo_encuesta(user)

    if request.method == 'POST':
        form = EncuestaForm(request.POST, tipo=tipo)
        if form.is_valid():
            data = form.cleaned_data
            user.first_name = data.get('first_name') or user.first_name
            user.last_name = data.get('last_name') or user.last_name
            if data.get('email'):
                user.email = data['email']
            user.encuesta_completada = True
            user.save(update_fields=['first_name', 'last_name', 'email', 'encuesta_completada'])
            if user.consentimiento_pedagogico:
                _crear_encuesta_estudiante(user, data, tipo)
            return redirect('ejercicios:home')
    else:
        form = EncuestaForm(tipo=tipo, initial={
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        })

    return render(request, 'registration/encuesta_onboarding.html', {
        'form': form,
        'tipo': tipo,
        'facultades_carreras_map': get_facultades_carreras_por_clave(),
    })


@login_required
def mi_perfil(request):
    """Vista de Mi Perfil: datos personales + cambio de contraseña voluntario."""
    perfil_form = PerfilForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'perfil':
            perfil_form = PerfilForm(request.POST, instance=request.user)
            if perfil_form.is_valid():
                perfil_form.save()
                messages.success(request, 'Datos actualizados correctamente.')
                return redirect('accounts:mi_perfil')

        elif accion == 'password':
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, 'Contraseña actualizada correctamente.')
                return redirect('accounts:mi_perfil')

    return render(request, 'registration/mi_perfil.html', {
        'perfil_form': perfil_form,
        'password_form': password_form,
    })


@login_required
def editar_encuesta(request):
    """Permite a lxs estudiantes corregir sus respuestas de onboarding.

    Los campos de lógica, el artículo de Xataka y la pregunta sobre qué es la
    ciencia se muestran como solo lectura (disabled) y sus valores se preservan
    desde la BD al guardar.
    """
    user = request.user
    if user.es_docente or user.is_staff:
        return redirect('ejercicios:home')
    if not user.encuesta_completada or not user.consentimiento_pedagogico:
        return redirect('accounts:mi_perfil')
    try:
        encuesta = user.encuesta
    except EncuestaEstudiante.DoesNotExist:
        return redirect('accounts:mi_perfil')

    tipo = _get_tipo_encuesta(user)

    if request.method == 'POST':
        form = EncuestaForm(request.POST, tipo=tipo, readonly_fields=_ENCUESTA_READONLY_FIELDS)
        if form.is_valid():
            data = form.cleaned_data
            # Restaurar campos protegidos desde la BD (disabled no envían valor)
            def _boolstr(v):
                return 'true' if v is True else 'false' if v is False else ''
            data['acertijo_silogismo'] = encuesta.acertijo_silogismo or ''
            data['acertijo_cirugia'] = encuesta.acertijo_cirugia or ''
            data['acertijo_hilera'] = encuesta.acertijo_hilera or ''
            data['articulo_risa'] = _boolstr(encuesta.articulo_risa)
            data['que_es_ciencia'] = encuesta.que_es_ciencia or ''

            user.first_name = data.get('first_name') or user.first_name
            user.last_name = data.get('last_name') or user.last_name
            if data.get('email'):
                user.email = data['email']
            user.save(update_fields=['first_name', 'last_name', 'email'])
            _crear_encuesta_estudiante(user, data, tipo)
            messages.success(request, 'Encuesta actualizada correctamente.')
            return redirect('accounts:mi_perfil')
    else:
        initial = _encuesta_to_initial(encuesta, user, tipo)
        form = EncuestaForm(tipo=tipo, readonly_fields=_ENCUESTA_READONLY_FIELDS, initial=initial)

    return render(request, 'registration/encuesta_onboarding.html', {
        'form': form,
        'tipo': tipo,
        'facultades_carreras_map': get_facultades_carreras_por_clave(),
        'modo_edicion': True,
    })
