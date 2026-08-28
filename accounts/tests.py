from datetime import datetime, timedelta
from pathlib import Path
import os
import re
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext, override as language_override

from accounts.facultades import get_carreras_unificadas_por_clave, get_facultades_carreras_por_clave
from accounts.forms import ConfiguracionEntornoForm, EncuestaForm
from accounts.installer import VARIABLES_ENTORNO
from accounts.models import CARRERA_CHOICES, ConfigSitio, EncuestaEstudiante
from cursos.models import Cohorte, Comision, Inscripcion
from logica_ipc.env_file import load_env_file


@override_settings(DEBUG=True, SETUP_TOKEN='')
class InstalacionInicialTests(TestCase):
    def _environment_data(self, **overrides):
        data = {
            'action': 'environment',
            'env-deployment_kind': 'managed',
            'env-secret_key': 'clave-secreta-larga-con-variedad-ABC-123-xyz-2026!',
            'env-setup_token': 'token-instalacion-muy-seguro-2026',
            'env-debug': 'False',
            'env-allowed_hosts': 'logica.example.org',
            'env-csrf_trusted_origins': 'https://logica.example.org',
            'env-database_url': 'postgresql://user:password@db.example.org/proplogplat',
            'env-use_database_url': 'True',
            'env-email_provider': 'none',
            'env-email_use_tls': 'True',
            'env-email_use_ssl': 'False',
            'env-trusted_proxy_count': '1',
            'env-port': '8000',
        }
        data.update(overrides)
        return data

    @override_settings(DEBUG=False, SETUP_TOKEN='clave-instalar')
    def test_asistente_crea_admin_configura_sitio_y_se_cierra(self):
        response = self.client.post(
            reverse('accounts:instalacion_inicial'),
            data={
                'token': 'clave-instalar',
                'nombre_sitio': 'Lógica abierta',
                'idioma_predeterminado': 'fr',
                'contacto_privacidad': 'privacidad@example.com',
                'color_primario': '#112233',
                'color_acento': '#445566',
                'cohorte_anio': '2030',
                'cohorte_cuatrimestre': '2',
                'error_consenso_min': '4',
                'umbral_riesgo': '8',
                'pistas_ia_activas': 'False',
                'revision_diccionario_activa': 'False',
                'username': 'primera-admin',
                'email': 'admin@example.com',
                'password1': 'ClaveSegura-2026!',
                'password2': 'ClaveSegura-2026!',
            },
        )

        self.assertRedirects(response, reverse('admin:index'))
        admin_user = get_user_model().objects.get(username='primera-admin')
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.es_docente)
        self.assertFalse(admin_user.debe_cambiar_password)
        config = ConfigSitio.get()
        self.assertTrue(config.instalacion_completada)
        self.assertEqual(config.nombre_sitio, 'Lógica abierta')
        self.assertEqual(config.idioma_predeterminado, 'fr')
        self.assertEqual(config.contacto_privacidad, 'privacidad@example.com')
        self.assertEqual(config.color_primario, '#112233')
        self.assertEqual(config.color_acento, '#445566')
        self.assertEqual(config.error_consenso_min, 4)
        self.assertEqual(config.umbral_riesgo, 8)
        self.assertFalse(config.pistas_ia_activas)
        self.assertFalse(config.revision_diccionario_activa)
        cohorte = Cohorte.objects.get(activa=True)
        self.assertTrue(cohorte.activa)
        self.assertEqual((cohorte.anio, cohorte.cuatrimestre), (2030, 2))

        config_admin = self.client.get(
            reverse('admin:accounts_configsitio_change', args=[config.pk])
        )
        self.assertEqual(config_admin.status_code, 200)
        self.assertContains(config_admin, 'umbral_riesgo')

        segunda_visita = self.client.get(reverse('accounts:instalacion_inicial'))
        self.assertRedirects(segunda_visita, reverse('accounts:login'))

    @override_settings(DEBUG=False, SETUP_TOKEN='')
    def test_produccion_sin_token_no_permite_instalar(self):
        response = self.client.get(reverse('accounts:instalacion_inicial'))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, 'SETUP_TOKEN', status_code=503)

    def test_idioma_admin_es_default_y_cookie_personal_tiene_precedencia(self):
        config = ConfigSitio.get()
        config.idioma_predeterminado = 'en'
        config.save(update_fields=['idioma_predeterminado'])

        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response['Content-Language'], 'en')
        self.assertContains(response, 'Incorrect username or password', count=0)
        self.assertContains(response, 'Log in')

        self.client.post(
            reverse('set_language'),
            {'language': 'de', 'next': reverse('accounts:login')},
        )
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response['Content-Language'], 'de')
        self.assertContains(response, 'Anmelden')

    def test_chino_se_puede_elegir_y_usa_el_catalogo_compilado(self):
        config = ConfigSitio.get()
        config.idioma_predeterminado = 'zh-hans'
        config.save(update_fields=['idioma_predeterminado'])

        response = self.client.get(reverse('accounts:login'))

        self.assertEqual(response['Content-Language'], 'zh-hans')
        self.assertContains(response, '登录')
        self.assertContains(response, '简体中文')

    def test_primera_entrada_a_la_portada_abre_el_instalador(self):
        response = self.client.get('/')

        self.assertRedirects(response, reverse('accounts:instalacion_inicial'))

        favicon = self.client.get(reverse('favicon'))
        self.assertEqual(favicon.status_code, 200)
        self.assertEqual(favicon['Content-Type'], 'image/svg+xml')

    def test_instalador_se_renderiza_en_todos_los_idiomas_y_enlaza_cafecito(self):
        expected = {
            'es': ('Revisar el despliegue', '¿Dónde está instalado?', 'Usuario administrador'),
            'en': ('Check the deployment', 'Where is it installed?', 'Administrator username'),
            'fr': ('Vérifier le déploiement', 'Où est-il installé ?', 'Identifiant administrateur'),
            'de': ('Bereitstellung prüfen', 'Wo ist es installiert?', 'Administrator-Benutzername'),
            'zh-hans': ('检查部署', '安装在哪里？', '管理员用户名'),
        }
        for language, texts in expected.items():
            with self.subTest(language=language):
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
                for step, text in zip(('diagnostico', 'entorno', 'sitio'), texts):
                    response = self.client.get(
                        reverse('accounts:instalacion_inicial') + f'?paso={step}'
                    )
                    self.assertContains(response, text)
                    self.assertContains(response, 'https://cafecito.app/jsgoyburu')
                    self.assertNotContains(response, 'ui.installer_')
                    self.assertNotContains(response, 'installer.')

                with language_override(language):
                    invalid = ConfiguracionEntornoForm(data={
                        'deployment_kind': 'managed',
                        'secret_key': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                        'setup_token': 'token-instalacion-valido',
                        'debug': 'False',
                        'allowed_hosts': 'https://dominio.example/ruta',
                        'use_database_url': 'True',
                        'email_provider': 'none',
                        'email_use_tls': 'True',
                        'email_use_ssl': 'False',
                        'trusted_proxy_count': '1',
                        'port': '8000',
                    })
                    self.assertFalse(invalid.is_valid())
                    self.assertNotIn('installer.', str(invalid.errors))

    def test_previsualiza_y_descarga_configuracion_portable_sin_cache(self):
        response = self.client.post(
            reverse('accounts:instalacion_inicial') + '?paso=entorno',
            data=self._environment_data(preview='1'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store, max-age=0')
        self.assertContains(response, 'SECRET_KEY=clave-secreta-larga')
        self.assertContains(response, 'DATABASE_URL=postgresql://user:password')

        download = self.client.post(
            reverse('accounts:instalacion_inicial') + '?paso=entorno',
            data=self._environment_data(download='1'),
        )
        self.assertEqual(download.status_code, 200)
        self.assertIn('attachment;', download['Content-Disposition'])
        self.assertEqual(download['Cache-Control'], 'no-store, max-age=0')
        self.assertIn(b'SETUP_TOKEN=', download.content)
        self.assertIn(b'DEBUG=False', download.content)

    def test_inventario_cubre_todas_las_variables_configurables(self):
        names = {name for name, _required, _secret, _description in VARIABLES_ENTORNO}
        self.assertEqual(names, {
            'SECRET_KEY', 'SETUP_TOKEN', 'DEBUG', 'ALLOWED_HOSTS',
            'CSRF_TRUSTED_ORIGINS', 'DATABASE_URL', 'USE_DATABASE_URL',
            'REDIS_URL', 'BREVO_API_KEY', 'EMAIL_HOST', 'EMAIL_PORT',
            'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD', 'EMAIL_USE_TLS',
            'EMAIL_USE_SSL', 'DEFAULT_FROM_EMAIL', 'TRUSTED_PROXY_COUNT',
            'GEMINI_API_KEY', 'GROQ_API_KEY', 'MCP_TRANSPORT',
            'MCP_ISSUER_URL', 'PORT', 'ADMIN_USERNAME', 'ADMIN_EMAIL',
            'ADMIN_PASSWORD',
        })

    @override_settings(DEBUG=False, SETUP_TOKEN='token-actual-seguro')
    def test_escritura_env_requiere_token_y_el_host_tiene_precedencia(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(BASE_DIR=Path(temp_dir)):
                invalid = self.client.post(
                    reverse('accounts:instalacion_inicial') + '?paso=entorno',
                    data=self._environment_data(**{
                        'env-write_to_server': 'on',
                        'env-authorization_token': 'incorrecto',
                        'preview': '1',
                    }),
                )
                self.assertFalse((Path(temp_dir) / '.env').exists())
                self.assertContains(invalid, 'SETUP_TOKEN actual no es válida')

                valid = self.client.post(
                    reverse('accounts:instalacion_inicial') + '?paso=entorno',
                    data=self._environment_data(**{
                        'env-write_to_server': 'on',
                        'env-authorization_token': 'token-actual-seguro',
                        'preview': '1',
                    }),
                )
                self.assertEqual(valid.status_code, 200)
                env_path = Path(temp_dir) / '.env'
                self.assertTrue(env_path.exists())
                self.assertIn('ALLOWED_HOSTS=logica.example.org', env_path.read_text('utf-8'))

                with patch.dict(os.environ, {'ALLOWED_HOSTS': 'host-inyectado'}, clear=False):
                    load_env_file(env_path)
                    self.assertEqual(os.environ['ALLOWED_HOSTS'], 'host-inyectado')


class CatalogosGettextTests(TestCase):
    """Toda clave usada por la UI debe existir en cada ``django.mo``."""

    IDIOMAS = ('es', 'en', 'fr', 'de', 'zh-hans')

    def test_todas_las_claves_de_templates_estan_en_los_cinco_mo(self):
        patron = re.compile(r"\{%\s*ui\s+'([^']+)'\s*%\}")
        claves = set()
        for ruta in (settings.BASE_DIR / 'templates').rglob('*.html'):
            claves.update(patron.findall(ruta.read_text(encoding='utf-8')))

        self.assertTrue(claves)
        for idioma in self.IDIOMAS:
            with language_override(idioma):
                faltantes = [
                    clave for clave in sorted(claves)
                    if gettext(f'ui.{clave}') == f'ui.{clave}'
                ]
            self.assertEqual(faltantes, [], f'{idioma}: claves sin traducir')

    def test_los_catalogos_compilados_forman_parte_del_repositorio(self):
        directorios = {'zh-hans': 'zh_Hans'}
        for idioma in self.IDIOMAS:
            directorio = directorios.get(idioma, idioma)
            mo = settings.BASE_DIR / 'locale' / directorio / 'LC_MESSAGES' / 'django.mo'
            self.assertTrue(mo.is_file(), f'Falta {mo}')
            self.assertGreater(mo.stat().st_size, 0)


class AccesoComisionTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.comision = Comision.objects.create(nombre='IPC comisión abierta')

    def test_get_muestra_opciones_login_y_registro(self):
        response = self.client.get(reverse('accounts:acceso_comision', args=[self.comision.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Iniciar sesión')
        self.assertContains(response, 'Registrarme como estudiante')

    def test_post_registro_crea_usuario_e_inscripcion(self):
        response = self.client.post(
            reverse('accounts:acceso_comision', args=[self.comision.id]),
            data={
                'username': 'est_nuevo',
                'email': 'est_nuevo@example.com',
                'first_name': 'Estu',
                'last_name': 'Nuevo',
                'password1': 'claveFuerte123',
                'password2': 'claveFuerte123',
            },
        )

        self.assertEqual(response.status_code, 302)
        user = self.User.objects.get(username='est_nuevo')
        self.assertFalse(user.es_docente)
        self.assertFalse(user.debe_cambiar_password)
        self.assertTrue(Inscripcion.objects.filter(estudiante=user, comision=self.comision).exists())

        destino = self.client.get(reverse('ejercicios:home'))
        self.assertRedirects(destino, reverse('accounts:consentimientos'))

    def test_post_registro_con_password_debil_muestra_error(self):
        response = self.client.post(
            reverse('accounts:acceso_comision', args=[self.comision.id]),
            data={
                'username': 'est_debil',
                'email': 'est_debil@example.com',
                'first_name': 'Estu',
                'last_name': 'Debil',
                'password1': '12345',
                'password2': '12345',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.User.objects.filter(username='est_debil').exists())
        self.assertContains(response, 'La contraseña es demasiado corta')

    def test_estudiante_logueado_que_entra_por_link_queda_inscripto(self):
        user = self.User.objects.create_user(
            username='est_existente',
            password='clave123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        self.client.login(username='est_existente', password='clave123')

        response = self.client.get(reverse('accounts:acceso_comision', args=[self.comision.id]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Inscripcion.objects.filter(estudiante=user, comision=self.comision).exists())


class AccesoComisionSinCohorteActivaTests(TestCase):
    """Code review (Hallazgo 3): sin cohorte activa (ventana entre
    cuatrimestres) este endpoint público no puede devolver un 500 crudo."""

    def setUp(self):
        self.User = get_user_model()
        self.comision = Comision.objects.create(nombre='IPC comisión sin cohorte activa')
        Cohorte.objects.filter(activa=True).update(activa=False)

    def test_post_registro_sin_cohorte_activa_no_crea_usuario_ni_revienta(self):
        response = self.client.post(
            reverse('accounts:acceso_comision', args=[self.comision.id]),
            data={
                'username': 'est_sin_cohorte',
                'email': 'est_sin_cohorte@example.com',
                'first_name': 'Estu',
                'last_name': 'SinCohorte',
                'password1': 'claveFuerte123',
                'password2': 'claveFuerte123',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.User.objects.filter(username='est_sin_cohorte').exists())
        self.assertFalse(Inscripcion.objects.filter(comision=self.comision).exists())
        self.assertContains(response, 'cuatrimestre activo')

    def test_estudiante_logueado_sin_cohorte_activa_no_revienta_ni_inscribe(self):
        user = self.User.objects.create_user(
            username='est_existente_sc',
            password='clave123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        self.client.login(username='est_existente_sc', password='clave123')

        response = self.client.get(
            reverse('accounts:acceso_comision', args=[self.comision.id]), follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Inscripcion.objects.filter(estudiante=user, comision=self.comision).exists())
        self.assertContains(response, 'cuatrimestre activo')


class AccesoComisionRecursanteTests(TestCase):
    """Hallazgo Important del review final: la cohorte es la camada de
    pertenencia, no el período del calendario (ver docstring de
    :class:`cursos.models.Cohorte`). Un estudiante que ya tiene inscripción
    en la comisión -de cualquier cohorte- no debe recibir una inscripción
    nueva en la cohorte activa al reabrir el link de acceso, porque eso lo
    convierte en recursante sin haberlo pedido y le resetea el progreso
    visible."""

    def setUp(self):
        self.User = get_user_model()
        self.comision = Comision.objects.create(nombre='IPC comisión recursante')
        self.cohorte_activa = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.cohorte_vieja, _ = Cohorte.objects.get_or_create(
            anio=2025, cuatrimestre=2, defaults={'activa': False},
        )

    def test_estudiante_con_inscripcion_en_cohorte_no_activa_no_recibe_una_nueva(self):
        user = self.User.objects.create_user(
            username='est_recursante',
            password='clave123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        Inscripcion.objects.create(
            estudiante=user, comision=self.comision, cohorte=self.cohorte_vieja,
        )
        self.client.login(username='est_recursante', password='clave123')

        response = self.client.get(reverse('accounts:acceso_comision', args=[self.comision.id]))

        self.assertEqual(response.status_code, 302)
        inscripciones = Inscripcion.objects.filter(estudiante=user, comision=self.comision)
        self.assertEqual(inscripciones.count(), 1)
        self.assertEqual(inscripciones.get().cohorte, self.cohorte_vieja)

    def test_estudiante_sin_inscripcion_en_la_comision_recibe_una_en_cohorte_activa(self):
        user = self.User.objects.create_user(
            username='est_nuevo_en_comision',
            password='clave123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        self.client.login(username='est_nuevo_en_comision', password='clave123')

        response = self.client.get(reverse('accounts:acceso_comision', args=[self.comision.id]))

        self.assertEqual(response.status_code, 302)
        inscripciones = Inscripcion.objects.filter(estudiante=user, comision=self.comision)
        self.assertEqual(inscripciones.count(), 1)
        self.assertEqual(inscripciones.get().cohorte, self.cohorte_activa)

    def test_registro_anonimo_sigue_creando_inscripcion(self):
        response = self.client.post(
            reverse('accounts:acceso_comision', args=[self.comision.id]),
            data={
                'username': 'est_registro_anonimo',
                'email': 'est_registro_anonimo@example.com',
                'first_name': 'Estu',
                'last_name': 'Anonimo',
                'password1': 'claveFuerte123',
                'password2': 'claveFuerte123',
            },
        )

        self.assertEqual(response.status_code, 302)
        user = self.User.objects.get(username='est_registro_anonimo')
        inscripciones = Inscripcion.objects.filter(estudiante=user, comision=self.comision)
        self.assertEqual(inscripciones.count(), 1)
        self.assertEqual(inscripciones.get().cohorte, self.cohorte_activa)


class FacultadesCarrerasMappingTests(TestCase):
    def test_mapea_facultades_a_carreras_de_choices(self):
        mapping = get_facultades_carreras_por_clave()

        self.assertIn('medicas', mapping)
        self.assertIn('medicina', mapping['medicas'])
        self.assertIn('radiologia', mapping['medicas'])

        self.assertIn('derecho', mapping)
        self.assertIn('abogacia', mapping['derecho'])


class EncuestaFormCarreraAnteriorTests(TestCase):
    def test_carrera_uba_anterior_usa_carreras_unificadas_del_json(self):
        form = EncuestaForm()
        opciones = form.fields['carrera_uba_anterior'].choices
        labels = dict(CARRERA_CHOICES)
        esperadas = [
            (clave, labels[clave])
            for clave in get_carreras_unificadas_por_clave()
        ]

        self.assertEqual(opciones[0], ('', '— Seleccioná tu carrera —'))
        self.assertEqual(opciones[1:], esperadas)


class EncuestaFormRecibidoUBAConditionalTests(TestCase):
    def test_limpia_respuesta_recibido_si_no_termino_cbc(self):
        form = EncuestaForm(
            tipo='basica',
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'termino_cbc_anterior': 'false',
                'se_recibio_uba': 'true',
            }
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['se_recibio_uba'], '')

    def test_conserva_respuesta_recibido_si_termino_cbc(self):
        form = EncuestaForm(
            tipo='basica',
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'termino_cbc_anterior': 'true',
                'se_recibio_uba': 'false',
            }
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['se_recibio_uba'], 'false')


class EncuestaFormRadioChoicesTests(TestCase):
    def test_radio_fields_no_incluyen_opcion_vacia(self):
        form = EncuestaForm()

        radio_fields = [
            name
            for name, field in form.fields.items()
            if field.widget.__class__.__name__ == 'RadioSelect'
        ]

        for field_name in radio_fields:
            choices = list(form.fields[field_name].choices)
            self.assertNotIn(('', ''), choices, msg=f"{field_name} incluye opción vacía")


class TipoEncuestaResolucionTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username='multi_comision',
            password='clave12345',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=False,
            debe_cambiar_password=False,
        )
        self.basica = Comision.objects.create(nombre='Basica', tipo_encuesta='basica')
        self.completa = Comision.objects.create(nombre='Completa', tipo_encuesta='completa')

    def test_prioriza_tipo_completa_si_hay_inscripcion_mixta(self):
        cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        Inscripcion.objects.create(estudiante=self.user, comision=self.basica, cohorte=cohorte)
        Inscripcion.objects.create(estudiante=self.user, comision=self.completa, cohorte=cohorte)
        self.client.login(username='multi_comision', password='clave12345')

        response = self.client.post(
            reverse('accounts:encuesta'),
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'facultad': 'derecho',
                'carrera': 'abogacia',
                'situacion_laboral': 'hasta_4',
                'dias_trabaja': '5',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.encuesta.situacion_laboral, 'hasta_4')
        self.assertEqual(self.user.encuesta.dias_trabaja, '5')


class EncuestaOnboardingPersistenciaTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.comision = Comision.objects.create(nombre='IPC completa', tipo_encuesta='completa')
        self.user = self.User.objects.create_user(
            username='encuesta_user',
            password='clave12345',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            consentimiento_contacto_seguimiento=False,
            encuesta_completada=False,
            debe_cambiar_password=False,
        )
        Inscripcion.objects.create(
            estudiante=self.user, comision=self.comision,
            cohorte=Cohorte.objects.get(anio=2026, cuatrimestre=1),
        )
        self.client.login(username='encuesta_user', password='clave12345')

    def test_get_no_muestra_desplegable_correo_electronico(self):
        response = self.client.get(reverse('accounts:encuesta'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<label for="id_email_tipo">Correo electrónico</label>', html=True)

    def test_post_tipo_escuela_bachillerato_no_rompe_por_longitud(self):
        response = self.client.post(
            reverse('accounts:encuesta'),
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'facultad': 'derecho',
                'carrera': 'abogacia',
                'tipo_escuela': 'bachillerato',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.encuesta_completada)
        self.assertEqual(self.user.encuesta.tipo_escuela, 'bachillerato')

    def test_post_laboral_guarda_valores_validos_en_modelo(self):
        response = self.client.post(
            reverse('accounts:encuesta'),
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'facultad': 'derecho',
                'carrera': 'abogacia',
                'situacion_laboral': 'hasta_4',
                'dias_trabaja': '5',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        encuesta = self.user.encuesta

        situacion_choices = dict(encuesta._meta.get_field('situacion_laboral').choices)
        dias_choices = dict(encuesta._meta.get_field('dias_trabaja').choices)

        self.assertEqual(encuesta.situacion_laboral, 'hasta_4')
        self.assertEqual(encuesta.dias_trabaja, '5')
        self.assertIn(encuesta.situacion_laboral, situacion_choices)
        self.assertIn(encuesta.dias_trabaja, dias_choices)

    def test_post_tiempo_desde_secundaria_guarda_valor_valido_en_modelo(self):
        response = self.client.post(
            reverse('accounts:encuesta'),
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'facultad': 'derecho',
                'carrera': 'abogacia',
                'tiempo_desde_secundaria': '1_3',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        encuesta = self.user.encuesta

        tiempo_choices = dict(encuesta._meta.get_field('tiempo_desde_secundaria').choices)

        self.assertEqual(encuesta.tiempo_desde_secundaria, '1_3')
        self.assertIn(encuesta.tiempo_desde_secundaria, tiempo_choices)

    def test_post_acertijo_silogismo_guarda_label_alineado_con_formulario(self):
        response = self.client.post(
            reverse('accounts:encuesta'),
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'facultad': 'derecho',
                'carrera': 'abogacia',
                'acertijo_silogismo': 'mas_bajo',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        encuesta = self.user.encuesta

        silogismo_choices = dict(encuesta._meta.get_field('acertijo_silogismo').choices)
        self.assertEqual(encuesta.acertijo_silogismo, 'mas_bajo')
        self.assertEqual(silogismo_choices['mas_bajo'], 'Más bajo')

    def test_post_acertijo_cirugia_no_se_guarda_respuesta_en_unico_campo(self):
        response = self.client.post(
            reverse('accounts:encuesta'),
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'facultad': 'derecho',
                'carrera': 'abogacia',
                'acertijo_cirugia_no_se': 'true',
                'acertijo_cirugia': 'La madre',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        encuesta = self.user.encuesta

        self.assertEqual(encuesta.acertijo_cirugia, 'No sé')
        self.assertNotIn('acertijo_cirugia_no_se', [field.name for field in EncuestaEstudiante._meta.fields])

    def test_post_tipo_inst_fuera_uba_otras_guarda_respuesta_en_unico_campo(self):
        response = self.client.post(
            reverse('accounts:encuesta'),
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'facultad': 'derecho',
                'carrera': 'abogacia',
                'tipo_inst_fuera_uba': 'otras',
                'tipo_inst_fuera_uba_otras': 'Academia comunitaria',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        encuesta = self.user.encuesta

        self.assertEqual(encuesta.tipo_inst_fuera_uba, 'Academia comunitaria')
        self.assertNotIn('tipo_inst_fuera_uba_otras', [field.name for field in EncuestaEstudiante._meta.fields])

    def test_post_motivo_no_termino_ipc_guarda_texto_legible_en_unico_campo(self):
        response = self.client.post(
            reverse('accounts:encuesta'),
            data={
                'last_name': 'Pérez',
                'first_name': 'Ana',
                'dni': '12345678',
                'facultad': 'derecho',
                'carrera': 'abogacia',
                'motivo_no_termino_ipc': 'priorice',
                'motivo_no_termino_ipc_otras': 'Ignorarme',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        encuesta = self.user.encuesta

        self.assertEqual(encuesta.motivo_no_termino_ipc, 'Priorizé la aprobación de otras materias')
        self.assertNotIn('motivo_no_termino_ipc_otras', [field.name for field in EncuestaEstudiante._meta.fields])


# ─── Tests: comentarios de template que se renderizan visibles ───────────────

class ComentariosDeTemplateNoVisiblesTests(TestCase):
    """Django solo trata ``{# ... #}`` como comentario si abre y cierra en la
    MISMA línea. Si se parte en dos, el motor no lo reconoce y el texto sale
    impreso en la página, a la vista del usuario.

    Este error ya ocurrió tres veces en el repo (``_filtros.html``,
    ``comision_detail.html``, ``_consentimientos_fields.html``), así que el
    guard es un barrido de todos los templates y no una aserción por archivo:
    un test por archivo no habría atrapado los dos que nadie estaba mirando.
    Para comentarios de varias líneas va ``{% comment %}...{% endcomment %}``.
    """

    def test_ningun_comentario_de_una_linea_queda_sin_cerrar(self):
        from django.conf import settings

        raiz = Path(settings.BASE_DIR) / 'templates'
        infractores = []
        for ruta in raiz.rglob('*.html'):
            for numero, linea in enumerate(
                ruta.read_text(encoding='utf-8').splitlines(), start=1
            ):
                if '{#' in linea and '#}' not in linea.split('{#', 1)[1]:
                    infractores.append(f'{ruta.relative_to(raiz)}:{numero}')

        self.assertEqual(
            infractores, [],
            'Comentarios {# #} abiertos sin cerrar en la misma línea: se '
            'renderizan visibles. Usar {% comment %}...{% endcomment %}.\n'
            + '\n'.join(infractores),
        )


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
        # El throttle cuenta en cache y la cache es global al proceso: sin
        # esto, un test le deja el contador cargado al siguiente.
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

    def test_el_asunto_trae_el_nombre_del_sitio(self):
        # No estaba en el plan: se agregó al ejecutarlo. El nombre llega por
        # `extra_email_context`, un mecanismo que no se ve desde el template y
        # que, si falla, deja el asunto cortado ("Recuperar tu contraseña de ")
        # sin que nada más se rompa. Los context processors no corren en los
        # mails, así que `config_sitio` no puede cubrirlo.
        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'olvido@ejemplo.com'},
        )
        self.assertIn(
            ConfigSitio.get().nombre_sitio,
            mail.outbox[0].subject,
        )

    def test_el_mail_respeta_el_idioma_elegido(self):
        self.client.post(
            reverse('set_language'),
            {'language': 'zh-hans', 'next': reverse('accounts:login')},
        )
        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'olvido@ejemplo.com'},
        )

        self.assertIn('重置', mail.outbox[0].subject)
        self.assertIn('24 小时', mail.outbox[0].body)

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

    def _link_del_ultimo_mail(self):
        self.assertTrue(mail.outbox, 'No llegó ningún mail.')
        for palabra in mail.outbox[-1].body.split():
            if '/accounts/reset/' in palabra:
                return palabra[palabra.index('/accounts/reset/'):]
        self.fail('El mail no contiene ningún link de reset.')

    def _link_de_reset(self):
        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'nuevo@ejemplo.com'},
        )
        return self._link_del_ultimo_mail()

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
        url_formulario = self.client.get(self._link_del_ultimo_mail())['Location']

        self.client.post(url_formulario, {
            'new_password1': 'clave-nueva-456',
            'new_password2': 'clave-nueva-456',
        })

        otro.refresh_from_db()
        self.assertFalse(otro.debe_cambiar_password)
        self.assertTrue(otro.check_password('clave-nueva-456'))


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

    def test_falsear_x_forwarded_for_no_abre_un_cupo_nuevo(self):
        """El techo por IP tiene que resistir un header falsificado.

        X-Forwarded-For lo puede escribir quien llama. El proxy de confianza
        agrega al FINAL la IP que realmente vio, así que lo de la izquierda es
        del cliente y no se puede creer. Si el techo se calculara con el primer
        valor, bastaría con cambiar el header en cada pedido para estrenar un
        contador y el límite no existiría.
        """
        for i in range(20):
            self.client.post(
                reverse('accounts:password_reset'),
                {'email': f'sondeo{i}@ejemplo.com'},
                HTTP_X_FORWARDED_FOR=f'10.0.0.{i}, 203.0.113.7',
            )

        self.client.post(
            reverse('accounts:password_reset'),
            {'email': 'olvido@ejemplo.com'},
            HTTP_X_FORWARDED_FOR='10.0.0.99, 203.0.113.7',
        )

        self.assertEqual(len(mail.outbox), 0)

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


class RecuperarPasswordEntradaTests(TestCase):
    """Si el link no está donde la persona se da cuenta del problema, no existe."""

    @override_settings(BREVO_API_KEY='api-configurada')
    def test_el_login_ofrece_recuperar_la_contrasena(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertContains(response, reverse('accounts:password_reset'))

    @override_settings(BREVO_API_KEY='api-configurada')
    def test_la_puerta_de_comision_tambien_lo_ofrece(self):
        comision = Comision.objects.create(nombre='IPC comisión de prueba')

        response = self.client.get(
            reverse('accounts:acceso_comision', args=[comision.id])
        )

        self.assertContains(response, reverse('accounts:password_reset'))

    @override_settings(BREVO_API_KEY='', EMAIL_HOST='')
    def test_sin_proveedor_no_anuncia_una_recuperacion_muda(self):
        login = self.client.get(reverse('accounts:login'))
        comision = Comision.objects.create(nombre='IPC sin correo')
        acceso = self.client.get(
            reverse('accounts:acceso_comision', args=[comision.id])
        )

        self.assertNotContains(login, reverse('accounts:password_reset'))
        self.assertNotContains(acceso, reverse('accounts:password_reset'))


class RecuperarPasswordFallaDeEnvioTests(TestCase):
    """Que el proveedor SMTP se caiga no puede delatar quién está registrado.

    Django ya cubre esto: PasswordResetForm.send_mail envuelve el send() en
    try/except y loguea. No es código nuestro, y por eso justamente se fija con
    un test: si alguien overridea send_mail, cambia de versión de Django o mueve
    el envío a la vista, la respuesta podría empezar a diferir entre una
    dirección registrada (500) y una que no lo está (302), y eso es un oráculo
    de enumeración que solo aparece cuando el proveedor está caído.
    """

    def setUp(self):
        self.User = get_user_model()
        self.User.objects.create_user(
            username='est_olvido',
            email='olvido@ejemplo.com',
            password='clave-vieja-123',
            consentimiento_pedagogico=True,
            consentimiento_investigacion=True,
            encuesta_completada=True,
        )
        cache.clear()

    def test_con_smtp_caido_la_respuesta_es_la_misma_exista_o_no_la_cuenta(self):
        import smtplib

        with patch(
            'django.core.mail.EmailMultiAlternatives.send',
            side_effect=smtplib.SMTPException('el proveedor no responde'),
        ):
            with self.assertLogs('django.contrib.auth', level='ERROR'):
                registrada = self.client.post(
                    reverse('accounts:password_reset'),
                    {'email': 'olvido@ejemplo.com'},
                )
            desconocida = self.client.post(
                reverse('accounts:password_reset'),
                {'email': 'nadie@ejemplo.com'},
            )

        destino = reverse('accounts:password_reset_done')
        self.assertRedirects(registrada, destino)
        self.assertRedirects(desconocida, destino)
