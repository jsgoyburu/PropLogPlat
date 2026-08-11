from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.facultades import get_carreras_unificadas_por_clave, get_facultades_carreras_por_clave
from accounts.forms import EncuestaForm
from accounts.models import CARRERA_CHOICES, ConfigSitio, EncuestaEstudiante
from cursos.models import Cohorte, Comision, Inscripcion


class InstalacionInicialTests(TestCase):
    @override_settings(DEBUG=False, SETUP_TOKEN='clave-instalar')
    def test_asistente_crea_admin_configura_sitio_y_se_cierra(self):
        response = self.client.post(
            reverse('accounts:instalacion_inicial'),
            data={
                'token': 'clave-instalar',
                'nombre_sitio': 'Lógica abierta',
                'idioma_predeterminado': 'fr',
                'contacto_privacidad': 'privacidad@example.com',
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
