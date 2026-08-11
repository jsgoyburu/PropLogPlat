import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from cursos.models import Cohorte, Comision, Inscripcion
from .models import Ejercicio, EjercicioPractica, Intento, Practica, PracticaComision, Progreso


def _u(username, password='clave123', **kwargs):
    """Crea usuario con consentimientos completados para pasar el middleware."""
    user = get_user_model().objects.create_user(username=username, password=password, **kwargs)
    get_user_model().objects.filter(pk=user.pk).update(
        consentimiento_pedagogico=True,
        consentimiento_investigacion=True,
        encuesta_completada=True,
    )
    user.refresh_from_db()
    return user


def _variables_libres(formula):
    """Variables libres de una fórmula, con el mismo parser que usa la API.

    Se apoya en motor.parser para respetar la notación del proyecto (p. ej.
    'v' es disyunción, no una variable). Devuelve un set vacío si la fórmula
    no parsea: en ese caso la API responde error_parse y ni siquiera llega a
    validar el diccionario.
    """
    from motor.parser import normalizar_simbolos, parsear
    try:
        return {s.name for s in parsear(normalizar_simbolos(formula).strip()).free_symbols}
    except ValueError:
        return set()


class PreviewVerificacionApiTests(TestCase):
    def setUp(self):
        self.user = _u('docente1', es_docente=True)
        self.client.login(username='docente1', password='clave123')

    def test_preview_verificacion_ok(self):
        response = self.client.post(
            reverse('ejercicios_api:preview-verificacion'),
            data={
                'formula_solucion': 'p ⊃ q',
                'respuesta_prueba': '~p ∨ q',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['correcto'])
        self.assertIsNone(payload['error_parse'])
        self.assertIsNotNone(payload['tabla_estudiante'])
        self.assertIsNotNone(payload['tabla_solucion'])

    def test_preview_verificacion_formula_solucion_invalida(self):
        response = self.client.post(
            reverse('ejercicios_api:preview-verificacion'),
            data={
                'formula_solucion': 'p && q',
                'respuesta_prueba': 'p',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn('formula_solucion', payload)


class MiHistorialViewTests(TestCase):
    def setUp(self):
        self.estudiante = _u('est-hist')
        self.docente = _u('doc-hist', es_docente=True)

        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Historial')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)

        self.practica = Practica.objects.create(titulo='Práctica Historial')
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)
        ejercicio = Ejercicio.objects.create(enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente)
        ep = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ejercicio, orden=1)
        Intento.objects.create(estudiante=self.estudiante, ejercicio_practica=ep, practica_comision=self.pc, cohorte=self.cohorte, respuesta_raw='p', es_correcto=True)

    def test_estudiante_ve_su_historial(self):
        self.client.login(username='est-hist', password='clave123')
        response = self.client.get(reverse('ejercicios:mi_historial'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mi historial de intentos')
        self.assertContains(response, 'Práctica Historial')

    def test_docente_redirige_a_dashboard(self):
        self.client.login(username='doc-hist', password='clave123')
        response = self.client.get(reverse('ejercicios:mi_historial'))
        self.assertEqual(response.status_code, 302)


class IntentoComentarioApiTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.docente = _u('doc-com', es_docente=True)
        self.otro_docente = _u('doc-otro', es_docente=True)
        self.admin = _u('admin-com', is_staff=True)
        self.estudiante = _u('est-com')

        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Comentarios')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)

        practica = Practica.objects.create(titulo='Práctica Comentarios')
        pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)
        ejercicio = Ejercicio.objects.create(enunciado='E', formula_solucion='p', tipo='formalizacion', creado_por=self.docente)
        ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.intento = Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=ep,
            practica_comision=pc,
            cohorte=self.cohorte,
            respuesta_raw='p',
            es_correcto=True,
        )

    def test_docente_de_comision_puede_comentar(self):
        self.client.login(username='doc-com', password='clave123')
        response = self.client.post(
            reverse('ejercicios_api:intento-comentario-update', args=[self.intento.id]),
            data={'comentario_docente': 'Buen trabajo'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.intento.refresh_from_db()
        self.assertEqual(self.intento.comentario_docente, 'Buen trabajo')

    def test_docente_fuera_de_comision_no_puede_comentar(self):
        self.client.login(username='doc-otro', password='clave123')
        response = self.client.post(
            reverse('ejercicios_api:intento-comentario-update', args=[self.intento.id]),
            data={'comentario_docente': 'Intento de edición'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_puede_comentar(self):
        self.client.login(username='admin-com', password='clave123')
        response = self.client.post(
            reverse('ejercicios_api:intento-comentario-update', args=[self.intento.id]),
            data={'comentario_docente': 'Revisado por admin'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.intento.refresh_from_db()
        self.assertEqual(self.intento.comentario_docente, 'Revisado por admin')


class DesbloqueoProgresivoTests(TestCase):
    """Cubre avanzar_progreso() y el desbloqueo en sus dos modos.

    Estructura del setUp: 1 práctica con 2 ejercicios, 1 estudiante inscripto.
    """

    def setUp(self):
        self.docente = _u('doc-prog-seq', es_docente=True)
        self.estudiante = _u('est-prog-seq')

        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Prog')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)

        self.practica = Practica.objects.create(titulo='P-seq')
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)
        ej1 = Ejercicio.objects.create(enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente)
        ej2 = Ejercicio.objects.create(enunciado='E2', formula_solucion='q', tipo='formalizacion', creado_por=self.docente)
        self.ep1 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej1, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej2, orden=2)

        self.client.login(username='est-prog-seq', password='clave123')

    def _intento(self, ep, respuesta, diccionario=None):
        """POSTea un intento de formalización con su diccionario.

        Desde e36d00d el backend rechaza (``correcto=False`` +
        ``error_diccionario``) toda formalización cuyo diccionario no cubra
        exactamente las variables libres de la fórmula enviada. Derivarlo de
        la respuesta mantiene estos tests apuntando a la corrección lógica y
        al desbloqueo, que es lo que esta clase cubre, en vez de chocar contra
        la validación del diccionario.
        """
        if diccionario is None:
            diccionario = {v: f'enunciado {v}' for v in _variables_libres(respuesta)}
        return self.client.post(
            reverse('ejercicios_api:intento-create'),
            data={
                'ejercicio_practica_id': ep.id,
                'practica_comision_id': self.pc.id,
                'respuesta_raw': respuesta,
                'diccionario': diccionario,
            },
            content_type='application/json',
        )

    def test_intento_correcto_crea_progreso_apuntando_a_siguiente(self):
        resp = self._intento(self.ep1, 'p')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['correcto'])


    def test_modo_libre_permite_resolver_fuera_de_orden(self):
        self.pc.desbloqueo_secuencial = False
        self.pc.save(update_fields=['desbloqueo_secuencial'])

        resp = self._intento(self.ep2, 'q')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['correcto'])
        # ep1 sigue sin resolver, así que el progreso queda apuntando ahí
        progreso = Progreso.objects.get(estudiante=self.estudiante, practica_comision=self.pc)
        self.assertEqual(progreso.ejercicio_practica_actual, self.ep1)
        self.assertEqual(resp.json()['ejercicios_pendientes'], 1)

    def test_modo_libre_completa_al_resolver_el_ultimo_pendiente(self):
        self.pc.desbloqueo_secuencial = False
        self.pc.save(update_fields=['desbloqueo_secuencial'])

        self._intento(self.ep2, 'q')
        resp = self._intento(self.ep1, 'p')

        self.assertTrue(resp.json()['practica_completa'])
        self.assertEqual(resp.json()['ejercicios_pendientes'], 0)
        progreso = Progreso.objects.get(estudiante=self.estudiante, practica_comision=self.pc)
        self.assertIsNone(progreso.ejercicio_practica_actual)

    def test_completar_ultimo_ejercicio_marca_practica_completa(self):
        # Resolver ep1 primero para que el progreso apunte a ep2
        Progreso.objects.create(
            estudiante=self.estudiante,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            ejercicio_practica_actual=self.ep2,
        )

        resp = self._intento(self.ep2, 'q')

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload['correcto'])
        self.assertTrue(payload['practica_completa'])
        progreso = Progreso.objects.get(estudiante=self.estudiante, practica_comision=self.pc)
        self.assertIsNone(progreso.ejercicio_practica_actual)

    def test_intento_incorrecto_no_crea_ni_avanza_progreso(self):
        # '~p' tiene tabla [False, True], distinta de 'p' → [True, False]: incorrecto.
        # No usar 'q' porque el motor acepta cualquier variable de 1 letra como
        # equivalente (misma forma proposicional, AGENTS.md §5).
        self._intento(self.ep1, '~p')  # incorrecto

        self.assertFalse(Progreso.objects.filter(estudiante=self.estudiante, practica_comision=self.pc).exists())

    def test_reintento_en_ejercicio_ya_resuelto_no_mueve_progreso(self):
        # Simular que el estudiante ya resolvió ep1 y está en ep2
        Progreso.objects.create(
            estudiante=self.estudiante,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            ejercicio_practica_actual=self.ep2,
        )

        # Reintento correcto en ep1 (ya resuelto)
        self._intento(self.ep1, 'p')

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica_comision=self.pc)
        # El progreso no retrocedió: sigue apuntando a ep2
        self.assertEqual(progreso.ejercicio_practica_actual, self.ep2)


class ReconciliarDisyuncionVCommandTests(TestCase):
    def setUp(self):
        self.docente = _u('doc-recalc', es_docente=True)
        self.estudiante = _u('est-recalc')

        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Recalc')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)

        self.practica = Practica.objects.create(titulo='P-recalc')
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)
        self.ej = Ejercicio.objects.create(
            enunciado='xor',
            formula_solucion='(JvM).~(J.M)',
            tipo='formalizacion',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(practica=self.practica, ejercicio=self.ej, orden=1)

    def test_reconciliacion_corrige_formula_e_intento_afectado(self):
        intento = Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            respuesta_raw='(JvM).~(J.M)',
            es_correcto=False,
        )

        call_command('reconciliar_disyuncion_v')

        self.ej.refresh_from_db()
        intento.refresh_from_db()
        self.assertEqual(self.ej.formula_solucion, '(J∨M).~(J.M)')
        self.assertEqual(intento.respuesta_raw, '(J∨M).~(J.M)')
        self.assertTrue(intento.es_correcto)

    def test_dry_run_no_persist_changes(self):
        intento = Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            respuesta_raw='(JvM).~(J.M)',
            es_correcto=False,
        )

        call_command('reconciliar_disyuncion_v', dry_run=True)

        self.ej.refresh_from_db()
        intento.refresh_from_db()
        self.assertEqual(self.ej.formula_solucion, '(JvM).~(J.M)')
        self.assertEqual(intento.respuesta_raw, '(JvM).~(J.M)')
        self.assertFalse(intento.es_correcto)

    def test_si_pasa_a_correcto_no_queda_autoaprobado_docente(self):
        intento = Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            respuesta_raw='(JvM).~(J.M)',
            es_correcto=False,
            aprobado_docente=False,
        )

        call_command('reconciliar_disyuncion_v')

        intento.refresh_from_db()
        self.assertTrue(intento.es_correcto)
        self.assertIsNone(intento.aprobado_docente)


class IntentoCreateViewTests(TestCase):
    """Verifica el check de inscripción en POST /api/intentos/."""

    def setUp(self):
        self.docente = _u('doc-intento', es_docente=True)
        self.estudiante_inscripto = _u('est-inscripto')
        self.estudiante_no_inscripto = _u('est-no-inscripto')

        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Intento')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante_inscripto, comision=self.comision, cohorte=self.cohorte)

        practica = Practica.objects.create(titulo='P1')
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar: llueve',
            formula_solucion='p',
            tipo='formalizacion',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)

    def _post_intento(self, respuesta='p'):
        return self.client.post(
            reverse('ejercicios_api:intento-create'),
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': self.pc.id,
                'respuesta_raw': respuesta,
            },
            content_type='application/json',
        )

    def test_estudiante_inscripto_puede_enviar_intento(self):
        self.client.login(username='est-inscripto', password='clave123')
        response = self._post_intento()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Intento.objects.filter(estudiante=self.estudiante_inscripto, ejercicio_practica=self.ep).exists())

    def test_estudiante_no_inscripto_recibe_403(self):
        self.client.login(username='est-no-inscripto', password='clave123')
        response = self._post_intento()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Intento.objects.filter(estudiante=self.estudiante_no_inscripto).exists())

    def test_no_autenticado_recibe_403(self):
        response = self._post_intento()
        # DRF con SessionAuthentication devuelve 403 para no autenticados
        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(Intento.objects.exists())


class GateFechasPorCohorteApiWritePathTests(TestCase):
    """Code review (Critical C1): el gate de fechas en POST /api/intentos/
    (write path) debe seguir el mismo criterio que el read path
    (ejercicios/views.py, ver GateFechasPorCohorteTests): fecha_apertura/
    fecha_cierre viven en PracticaComision, que pertenece al aula y se
    comparte entre camadas, así que solo aplican a la cohorte activa.

    Antes del fix, el endpoint aplicaba el gate sin condicionarlo a la
    cohorte: alguien de una camada cerrada podía abrir la práctica (200,
    read path ya corregido) pero cada envío le devolvía 403 (write path sin
    corregir) — peor que no dejarlo entrar."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone

        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        Cohorte.objects.filter(pk=self.c1.pk).update(activa=False)
        Cohorte.objects.filter(pk=self.c2.pk).update(activa=True)

        self.comision = Comision.objects.create(nombre='IPC Gate API')
        self.est_vieja = _u('final-api-c1')
        self.est_actual = _u('cursa-api-c2')
        Inscripcion.objects.create(estudiante=self.est_vieja, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est_actual, comision=self.comision, cohorte=self.c2)

        practica = Practica.objects.create(titulo='P-gate-api')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
            fecha_cierre=timezone.now() - timedelta(days=1),
        )

    def _post_intento(self, respuesta='p'):
        return self.client.post(
            reverse('ejercicios_api:intento-create'),
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': self.pc.id,
                'respuesta_raw': respuesta,
            },
            content_type='application/json',
        )

    def test_camada_vieja_puede_enviar_intento_aunque_la_practica_este_cerrada(self):
        self.client.login(username='final-api-c1', password='clave123')
        response = self._post_intento()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Intento.objects.filter(estudiante=self.est_vieja, ejercicio_practica=self.ep).exists()
        )

    def test_cohorte_activa_sigue_bloqueada_por_el_cierre(self):
        self.client.login(username='cursa-api-c2', password='clave123')
        response = self._post_intento()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'La práctica ya cerró.')
        self.assertFalse(Intento.objects.filter(estudiante=self.est_actual).exists())

    def test_camada_vieja_puede_enviar_aunque_la_practica_aun_no_haya_abierto(self):
        """Mismo problema en la rama `no_iniciada`: se cubre por separado
        porque es una condición distinta dentro de la misma vista."""
        from datetime import timedelta
        from django.utils import timezone

        self.pc.fecha_cierre = None
        self.pc.fecha_apertura = timezone.now() + timedelta(days=1)
        self.pc.save(update_fields=['fecha_cierre', 'fecha_apertura'])

        self.client.login(username='final-api-c1', password='clave123')
        response = self._post_intento()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Intento.objects.filter(estudiante=self.est_vieja, ejercicio_practica=self.ep).exists()
        )


class PreviewArgumentoApiTests(TestCase):
    """Verifica el endpoint POST /api/preview-argumento/ tras aplicar
    validar_parentesis_en_operaciones_mixtas() en verificar_argumento().
    """

    def setUp(self):
        self.user = _u('doc-arg-prev', es_docente=True)
        self.client.login(username='doc-arg-prev', password='clave123')

    def test_preview_argumento_ok(self):
        """Modus Ponens: argumento válido → correcto=True y tabla devuelta."""
        response = self.client.post(
            reverse('ejercicios_api:preview-argumento'),
            data={
                'enunciados_prueba': [
                    {'formula': 'p ⊃ q', 'tipo': 'premisa'},
                    {'formula': 'p', 'tipo': 'premisa'},
                    {'formula': 'q', 'tipo': 'conclusion'},
                ],
                'juicio_valido': True,
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['correcto'])
        self.assertTrue(payload['es_valido'])
        self.assertIsNotNone(payload['tabla_argumento'])

    def test_preview_argumento_operaciones_mixtas_sin_parentesis_devuelve_error_parse(self):
        """p ∨ q · r sin paréntesis debe quedar capturada en errores_parse.

        Antes del fix a verificar_argumento(), validar_parentesis_en_operaciones_mixtas()
        no se aplicaba a las fórmulas de argumentos. Tras el fix, el error se
        detecta y se devuelve en errores_parse en lugar de parsear ambiguamente.
        """
        response = self.client.post(
            reverse('ejercicios_api:preview-argumento'),
            data={
                'enunciados_prueba': [
                    {'formula': 'p ∨ q · r', 'tipo': 'premisa'},
                    {'formula': 's', 'tipo': 'conclusion'},
                ],
                'juicio_valido': None,
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['correcto'])
        # El primer enunciado debe tener error de parseo
        self.assertIsNotNone(payload['errores_parse'][0])


class ReevaluarTablasVerdadCommandTests(TestCase):
    def setUp(self):
        self.docente = _u('doc-reeval', es_docente=True)
        self.estudiante = _u('est-reeval')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Reeval')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)

        self.practica = Practica.objects.create(titulo='Argumentos reeval')
        self.pc = PracticaComision.objects.create(
            practica=self.practica,
            comision=self.comision,
            orden=1,
        )

        self.solucion = [
            {'formula': 'P->(R&D)', 'tipo': 'premisa'},
            {'formula': '~D&R', 'tipo': 'premisa'},
            {'formula': 'P', 'tipo': 'conclusion'},
        ]
        self.estudiante_argumento = [
            {'formula': 'E->(R&D)', 'tipo': 'premisa'},
            {'formula': '~D&R', 'tipo': 'premisa'},
            {'formula': 'E', 'tipo': 'conclusion'},
        ]
        ejercicio_tabla = Ejercicio.objects.create(
            enunciado='Argumento con renombramiento de variables',
            formula_solucion=json.dumps(self.solucion),
            tipo='tabla_verdad',
            creado_por=self.docente,
        )
        ejercicio_siguiente = Ejercicio.objects.create(
            enunciado='Siguiente ejercicio',
            formula_solucion='p',
            tipo='formalizacion',
            creado_por=self.docente,
        )
        ejercicio_tercero = Ejercicio.objects.create(
            enunciado='Tercer ejercicio',
            formula_solucion='q',
            tipo='formalizacion',
            creado_por=self.docente,
        )
        self.ep_tabla = EjercicioPractica.objects.create(
            practica=self.practica,
            ejercicio=ejercicio_tabla,
            orden=1,
        )
        self.ep_siguiente = EjercicioPractica.objects.create(
            practica=self.practica,
            ejercicio=ejercicio_siguiente,
            orden=2,
        )
        self.ep_tercero = EjercicioPractica.objects.create(
            practica=self.practica,
            ejercicio=ejercicio_tercero,
            orden=3,
        )

    def _crear_intento_renombrado(self):
        from motor import verificar_argumento

        tabla_estudiante = verificar_argumento(
            self.estudiante_argumento,
            self.estudiante_argumento,
            False,
        )['tabla_canonica']
        return Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ep_tabla,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            respuesta_raw=json.dumps(self.estudiante_argumento),
            es_correcto=False,
            tabla_json=tabla_estudiante,
            juicio_estudiante=False,
        )

    def test_reevalua_tabla_verdad_y_avanza_progreso(self):
        intento = self._crear_intento_renombrado()
        Progreso.objects.create(
            estudiante=self.estudiante,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            ejercicio_practica_actual=self.ep_tabla,
        )

        stdout = StringIO()
        call_command('reevaluar_tablas_verdad', stdout=stdout)

        intento.refresh_from_db()
        self.assertTrue(intento.es_correcto)
        self.assertIsNone(intento.aprobado_docente)

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica_comision=self.pc)
        self.assertEqual(progreso.ejercicio_practica_actual, self.ep_siguiente)

    def test_reevaluar_no_retrocede_si_el_progreso_ya_esta_mas_adelante(self):
        intento = self._crear_intento_renombrado()
        Progreso.objects.create(
            estudiante=self.estudiante,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            ejercicio_practica_actual=self.ep_tercero,
        )

        stdout = StringIO()
        call_command('reevaluar_tablas_verdad', stdout=stdout)

        intento.refresh_from_db()
        self.assertTrue(intento.es_correcto)

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica_comision=self.pc)
        self.assertEqual(progreso.ejercicio_practica_actual, self.ep_tercero)

    def test_reevalua_crea_progreso_con_cohorte_cuando_no_existe(self):
        """Code review (Hallazgo 2): sin Progreso preexistente, el comando debe
        poder crearlo con la cohorte del propio intento, sin IntegrityError."""
        intento = self._crear_intento_renombrado()
        self.assertFalse(
            Progreso.objects.filter(estudiante=self.estudiante, practica_comision=self.pc).exists()
        )

        stdout = StringIO()
        call_command('reevaluar_tablas_verdad', stdout=stdout)

        intento.refresh_from_db()
        self.assertTrue(intento.es_correcto)

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica_comision=self.pc)
        self.assertEqual(progreso.cohorte, self.cohorte)
        self.assertEqual(progreso.ejercicio_practica_actual, self.ep_siguiente)

from unittest.mock import patch


class IntentoCreatePistaGeminiTests(TestCase):
    def setUp(self):
        self.docente = _u('doc-pista', es_docente=True)
        self.estudiante = _u('est-pista')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Pista')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)

        practica = Practica.objects.create(titulo='Practica Pista')
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizá una condicional simple',
            formula_solucion='p',
            tipo='formalizacion',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.client.login(username='est-pista', password='clave123')

    def _intento_incorrecto(self):
        return self.client.post(
            reverse('ejercicios_api:intento-create'),
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': self.pc.id,
                'respuesta_raw': '~p',
                'diccionario': {'p': 'llueve'},
            },
            content_type='application/json',
        )

    @patch('ejercicios.api.views.generar_pista_gemini', return_value='¿Cuál es el conectivo principal de tu fórmula?')
    def test_incluye_pista_a_partir_del_quinto_intento_incorrecto(self, _mock_pista):
        # Desde a764e06 la pista se emite recién en el 5.º intento incorrecto
        # del ejercicio (el conteo incluye el intento actual, ya guardado).
        for _ in range(4):
            resp = self._intento_incorrecto()
            self.assertEqual(resp.status_code, 200)
            self.assertIsNone(resp.json()['pista'])

        resp = self._intento_incorrecto()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['correcto'])
        self.assertEqual(data['pista'], '¿Cuál es el conectivo principal de tu fórmula?')

    @patch('ejercicios.api.views.generar_pista_gemini', return_value='No debería usarse')
    def test_no_genera_pista_si_intento_correcto(self, mock_pista):
        resp = self.client.post(
            reverse('ejercicios_api:intento-create'),
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': self.pc.id,
                'respuesta_raw': 'p',
                'diccionario': {'p': 'llueve'},
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['correcto'])
        self.assertIsNone(data['pista'])
        mock_pista.assert_not_called()

from django.utils import timezone
from datetime import timedelta
from mcp_intentos import _listar_intentos_impl


class MCPPaginacionListarIntentosTests(TestCase):
    def setUp(self):
        self.docente = _u('doc-mcp', es_docente=True)
        self.estudiante = _u('est-mcp')
        get_user_model().objects.filter(pk=self.estudiante.pk).update(research_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
        self.estudiante.refresh_from_db()

        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC MCP')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)

        practica = Practica.objects.create(titulo='Práctica MCP')
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)
        self.ej1 = Ejercicio.objects.create(enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente)
        self.ej2 = Ejercicio.objects.create(enunciado='E2', formula_solucion='q', tipo='formalizacion', creado_por=self.docente)
        self.ep1 = EjercicioPractica.objects.create(practica=practica, ejercicio=self.ej1, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=practica, ejercicio=self.ej2, orden=2)

        base = timezone.now()
        for idx in range(25):
            intento = Intento.objects.create(
                estudiante=self.estudiante,
                ejercicio_practica=self.ep1 if idx % 2 == 0 else self.ep2,
                practica_comision=self.pc,
                cohorte=self.cohorte,
                respuesta_raw=f'r{idx}',
                es_correcto=(idx % 3 == 0),
                aprobado_docente=None,
            )
            Intento.objects.filter(pk=intento.pk).update(timestamp=base - timedelta(minutes=idx))

    def test_listar_intentos_primer_bloque_con_limit(self):
        page = _listar_intentos_impl(limit=10)
        self.assertEqual(len(page), 10)

    def test_listar_intentos_segundo_bloque_con_offset(self):
        p1 = _listar_intentos_impl(limit=10, offset=0)
        p2 = _listar_intentos_impl(limit=10, offset=10)
        self.assertEqual(len(p2), 10)
        ids1 = {x['id'] for x in p1}
        ids2 = {x['id'] for x in p2}
        self.assertTrue(ids1.isdisjoint(ids2))

    def test_filtros_siguen_funcionando_con_offset(self):
        filtered = _listar_intentos_impl(ejercicio_id=self.ej1.id, solo_incorrectos=True, limit=5, offset=2)
        self.assertLessEqual(len(filtered), 5)
        self.assertTrue(all(item['ejercicio_id'] == self.ej1.id for item in filtered))
        self.assertTrue(all(item['es_correcto'] is False for item in filtered))

    def test_offset_default_mantiene_compatibilidad(self):
        explicit = _listar_intentos_impl(limit=7, offset=0)
        default = _listar_intentos_impl(limit=7)
        self.assertEqual([x['id'] for x in explicit], [x['id'] for x in default])


class CorrectitudEfectivaTests(TestCase):
    """El juicio docente tiene precedencia sobre el resultado del motor."""

    def setUp(self):
        self.estudiante = _u('alu-correctitud')
        docente = _u('doc-correctitud', es_docente=True)
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        comision = Comision.objects.create(nombre='IPC Correctitud')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=comision, cohorte=self.cohorte)
        practica = Practica.objects.create(titulo='P', creada_por=docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=comision, orden=1,
        )
        ejercicio = Ejercicio.objects.create(
            enunciado='E', formula_solucion='p', tipo='formalizacion', creado_por=docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=practica, ejercicio=ejercicio, orden=1,
        )

    def _intento(self, es_correcto, aprobado_docente):
        return Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=self.cohorte,
            respuesta_raw='p',
            es_correcto=es_correcto,
            aprobado_docente=aprobado_docente,
        )

    def test_correcto_sin_revisar_cuenta_como_correcto(self):
        from ejercicios.correctitud import Q_CORRECTO
        intento = self._intento(es_correcto=True, aprobado_docente=None)
        self.assertTrue(Intento.objects.filter(Q_CORRECTO, pk=intento.pk).exists())

    def test_correcto_rechazado_por_docente_no_cuenta(self):
        from ejercicios.correctitud import Q_CORRECTO
        intento = self._intento(es_correcto=True, aprobado_docente=False)
        self.assertFalse(Intento.objects.filter(Q_CORRECTO, pk=intento.pk).exists())

    def test_incorrecto_aprobado_por_docente_cuenta_como_correcto(self):
        from ejercicios.correctitud import Q_CORRECTO
        intento = self._intento(es_correcto=False, aprobado_docente=True)
        self.assertTrue(Intento.objects.filter(Q_CORRECTO, pk=intento.pk).exists())

    def test_incorrecto_sin_revisar_no_cuenta(self):
        from ejercicios.correctitud import Q_CORRECTO
        intento = self._intento(es_correcto=False, aprobado_docente=None)
        self.assertFalse(Intento.objects.filter(Q_CORRECTO, pk=intento.pk).exists())

    def test_q_incorrecto_es_el_complemento(self):
        from ejercicios.correctitud import Q_CORRECTO, Q_INCORRECTO
        self._intento(es_correcto=True, aprobado_docente=None)
        self._intento(es_correcto=True, aprobado_docente=False)
        self._intento(es_correcto=False, aprobado_docente=True)
        self._intento(es_correcto=False, aprobado_docente=None)

        correctos = Intento.objects.filter(Q_CORRECTO).count()
        incorrectos = Intento.objects.filter(Q_INCORRECTO).count()

        self.assertEqual(correctos, 2)
        self.assertEqual(incorrectos, 2)


class DesbloqueoConfigurableModeloTests(TestCase):
    def test_default_es_secuencial(self):
        docente = _u('doc-modo', es_docente=True)
        comision = Comision.objects.create(nombre='IPC Modo')
        practica = Practica.objects.create(titulo='P', creada_por=docente)
        pc = PracticaComision.objects.create(practica=practica, comision=comision, orden=1)

        self.assertTrue(pc.desbloqueo_secuencial)

    def test_se_puede_poner_en_libre(self):
        docente = _u('doc-modo-libre', es_docente=True)
        comision = Comision.objects.create(nombre='IPC Modo Libre')
        practica = Practica.objects.create(titulo='P', creada_por=docente)
        pc = PracticaComision.objects.create(
            practica=practica, comision=comision, orden=1,
            desbloqueo_secuencial=False,
        )
        pc.refresh_from_db()

        self.assertFalse(pc.desbloqueo_secuencial)


class ProgresoModuloTests(TestCase):
    """avanzar_progreso() en ambos modos, sin pasar por la API."""

    def setUp(self):
        self.docente = _u('doc-mod', es_docente=True)
        self.estudiante = _u('est-mod')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Mod')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)
        self.practica = Practica.objects.create(titulo='P-mod', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )
        self.eps = []
        for i in (1, 2, 3):
            ej = Ejercicio.objects.create(
                enunciado=f'E{i}', formula_solucion='p',
                tipo='formalizacion', creado_por=self.docente,
            )
            self.eps.append(EjercicioPractica.objects.create(
                practica=self.practica, ejercicio=ej, orden=i,
            ))

    def _resolver(self, ep, aprobado_docente=None, es_correcto=True):
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=ep,
            practica_comision=self.pc, cohorte=self.cohorte, respuesta_raw='p',
            es_correcto=es_correcto, aprobado_docente=aprobado_docente,
        )

    def _modo(self, secuencial):
        """Fija el modo de desbloqueo del pc de la práctica."""
        self.pc.desbloqueo_secuencial = secuencial
        self.pc.save(update_fields=['desbloqueo_secuencial'])

    def test_secuencial_avanza_al_siguiente(self):
        from ejercicios.progreso import avanzar_progreso
        self._modo(True)
        Progreso.objects.create(
            estudiante=self.estudiante, cohorte=self.cohorte,
            practica_comision=self.pc, ejercicio_practica_actual=self.eps[0],
        )
        self._resolver(self.eps[0])

        completa, pendientes = avanzar_progreso(self.estudiante, self.eps[0], self.pc, self.cohorte)

        progreso = Progreso.objects.get(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte,
        )
        self.assertEqual(progreso.ejercicio_practica_actual, self.eps[1])
        self.assertFalse(completa)
        self.assertEqual(pendientes, 2)

    def test_secuencial_no_retrocede_al_reintentar_resuelto(self):
        from ejercicios.progreso import avanzar_progreso
        self._modo(True)
        Progreso.objects.create(
            estudiante=self.estudiante, cohorte=self.cohorte,
            practica_comision=self.pc, ejercicio_practica_actual=self.eps[2],
        )
        self._resolver(self.eps[0])

        avanzar_progreso(self.estudiante, self.eps[0], self.pc, self.cohorte)

        progreso = Progreso.objects.get(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte,
        )
        self.assertEqual(progreso.ejercicio_practica_actual, self.eps[2])

    def test_libre_resolver_el_tercero_deja_el_actual_en_el_primero(self):
        from ejercicios.progreso import avanzar_progreso
        self._modo(False)
        self._resolver(self.eps[2])

        completa, pendientes = avanzar_progreso(self.estudiante, self.eps[2], self.pc, self.cohorte)

        progreso = Progreso.objects.get(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte,
        )
        self.assertEqual(progreso.ejercicio_practica_actual, self.eps[0])
        self.assertFalse(completa)
        self.assertEqual(pendientes, 2)

    def test_libre_resolver_el_ultimo_pendiente_completa_la_practica(self):
        from ejercicios.progreso import avanzar_progreso
        self._modo(False)
        for ep in self.eps:
            self._resolver(ep)

        completa, pendientes = avanzar_progreso(self.estudiante, self.eps[1], self.pc, self.cohorte)

        progreso = Progreso.objects.get(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte,
        )
        self.assertIsNone(progreso.ejercicio_practica_actual)
        self.assertTrue(completa)
        self.assertEqual(pendientes, 0)

    def test_esta_resuelto_respeta_el_juicio_docente(self):
        from ejercicios.progreso import esta_resuelto
        self._resolver(self.eps[0], aprobado_docente=False)
        self.assertFalse(esta_resuelto(self.estudiante, self.eps[0], self.pc, self.cohorte))
        self._resolver(self.eps[1], es_correcto=False, aprobado_docente=True)
        self.assertTrue(esta_resuelto(self.estudiante, self.eps[1], self.pc, self.cohorte))


class DesbloqueoLibreVistasTests(TestCase):
    def setUp(self):
        self.docente = _u('doc-libre', es_docente=True)
        self.estudiante = _u('est-libre')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Libre')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)
        self.practica = Practica.objects.create(titulo='P-libre', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
            desbloqueo_secuencial=False,
        )
        ej1 = Ejercicio.objects.create(enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente)
        ej2 = Ejercicio.objects.create(enunciado='E2', formula_solucion='q', tipo='formalizacion', creado_por=self.docente)
        self.ep1 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej1, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej2, orden=2)
        self.client.login(username='est-libre', password='clave123')

    def test_ningun_ejercicio_queda_bloqueado(self):
        response = self.client.get(reverse('ejercicios:practica', args=[self.pc.id]))

        self.assertEqual(response.status_code, 200)
        estados = [d['estado'] for d in response.context['eps_data']]
        self.assertNotIn('bloqueado', estados)

    def test_se_puede_entrar_al_segundo_sin_resolver_el_primero(self):
        response = self.client.get(
            reverse('ejercicios:ejercicio', args=[self.pc.id, self.ep2.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['puede_enviar'])

    def test_secuencial_sigue_bloqueando(self):
        self.pc.desbloqueo_secuencial = True
        self.pc.save(update_fields=['desbloqueo_secuencial'])

        detalle = self.client.get(reverse('ejercicios:practica', args=[self.pc.id]))
        self.assertIn('bloqueado', [d['estado'] for d in detalle.context['eps_data']])

        response = self.client.get(
            reverse('ejercicios:ejercicio', args=[self.pc.id, self.ep2.id])
        )
        self.assertEqual(response.status_code, 302)


class BackfillIndicesTests(TestCase):
    """construir_indices() arma los dos mapas que usan las reglas."""

    def setUp(self):
        self.docente = _u('doc-bf-idx', es_docente=True)
        self.estudiante = _u('est-bf-idx')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='C-bf-idx')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)
        self.practica = Practica.objects.create(titulo='P-bf-idx', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )

    def test_indices_mapean_practica_a_pcs_y_estudiante_a_comisiones(self):
        from ejercicios.backfill import construir_indices
        pcs_por_practica, comisiones_por_estudiante = construir_indices(
            PracticaComision, Inscripcion,
        )

        self.assertEqual(
            pcs_por_practica[self.practica.id],
            [(self.pc.id, self.comision.id)],
        )
        self.assertEqual(
            comisiones_por_estudiante[self.estudiante.id],
            {self.comision.id},
        )


class BackfillAtribucionIntentoTests(TestCase):
    """pc_para_intento(): reglas 1 (inscripción única) y 2 (práctica única)."""

    def setUp(self):
        self.docente = _u('doc-bf-int', es_docente=True)
        self.estudiante = _u('est-bf-int')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision_a = Comision.objects.create(nombre='C-bf-A')
        self.comision_b = Comision.objects.create(nombre='C-bf-B')
        self.practica = Practica.objects.create(titulo='P-bf-int', creada_por=self.docente)

    def _indices(self):
        from ejercicios.backfill import construir_indices
        return construir_indices(PracticaComision, Inscripcion)

    def test_regla_1_inscripcion_unica(self):
        from ejercicios.backfill import pc_para_intento
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)
        pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        # La práctica también está en B, pero el estudiante no está en B.
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        resultado = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id,
        )

        self.assertEqual(resultado, pc_a.id)

    def test_regla_2_desinscripto_con_practica_en_una_sola_comision(self):
        from ejercicios.backfill import pc_para_intento
        # El estudiante no está inscripto en ninguna comisión.
        pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        resultado = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id,
        )

        self.assertEqual(resultado, pc_a.id)

    def test_ambiguo_devuelve_none(self):
        from ejercicios.backfill import pc_para_intento
        # Inscripto en las dos comisiones que comparten la práctica.
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b, cohorte=self.cohorte)
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        resultado = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id,
        )

        self.assertIsNone(resultado)

    def test_desinscripto_y_practica_en_dos_comisiones_devuelve_none(self):
        from ejercicios.backfill import pc_para_intento
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        resultado = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id,
        )

        self.assertIsNone(resultado)


class BackfillCandidatosProgresoTests(TestCase):
    """pcs_candidatos(): solo inscripción, sin el fallback de la regla 2."""

    def setUp(self):
        self.docente = _u('doc-bf-cand', es_docente=True)
        self.estudiante = _u('est-bf-cand')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision_a = Comision.objects.create(nombre='C-cand-A')
        self.comision_b = Comision.objects.create(nombre='C-cand-B')
        self.practica = Practica.objects.create(titulo='P-cand', creada_por=self.docente)

    def _indices(self):
        from ejercicios.backfill import construir_indices
        return construir_indices(PracticaComision, Inscripcion)

    def test_n1_devuelve_un_candidato(self):
        from ejercicios.backfill import pcs_candidatos
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)
        pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        self.assertEqual(
            pcs_candidatos(pcs_por_practica, comisiones_por_estudiante,
                           self.practica.id, self.estudiante.id),
            [pc_a.id],
        )

    def test_n0_sin_inscripcion_devuelve_vacio(self):
        from ejercicios.backfill import pcs_candidatos
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        self.assertEqual(
            pcs_candidatos(pcs_por_practica, comisiones_por_estudiante,
                           self.practica.id, self.estudiante.id),
            [],
        )

    def test_n2_devuelve_los_dos(self):
        from ejercicios.backfill import pcs_candidatos
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b, cohorte=self.cohorte)
        pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        self.assertEqual(
            sorted(pcs_candidatos(pcs_por_practica, comisiones_por_estudiante,
                                  self.practica.id, self.estudiante.id)),
            sorted([pc_a.id, pc_b.id]),
        )


class BackfillPunteroTests(TestCase):
    """puntero_reconstruido(): primer EP por orden sin resolver en ese pc."""

    def setUp(self):
        self.docente = _u('doc-bf-pt', es_docente=True)
        self.estudiante = _u('est-bf-pt')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='C-pt')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)
        self.practica = Practica.objects.create(titulo='P-pt', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )
        self.eps = []
        for i in (1, 2, 3):
            ej = Ejercicio.objects.create(
                enunciado=f'E{i}', formula_solucion='p',
                tipo='formalizacion', creado_por=self.docente,
            )
            self.eps.append(EjercicioPractica.objects.create(
                practica=self.practica, ejercicio=ej, orden=i,
            ))

    def test_sin_intentos_apunta_al_primero(self):
        from ejercicios.backfill import puntero_reconstruido
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[0].id)

    def test_resuelto_el_primero_apunta_al_segundo(self):
        from ejercicios.backfill import puntero_reconstruido
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc, cohorte=self.cohorte, respuesta_raw='p',
            es_correcto=True, aprobado_docente=None,
        )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[1].id)

    def test_incorrecto_aprobado_por_docente_cuenta_como_resuelto(self):
        from ejercicios.backfill import puntero_reconstruido
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc, cohorte=self.cohorte, respuesta_raw='zzz',
            es_correcto=False, aprobado_docente=True,
        )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[1].id)

    def test_correcto_rechazado_por_docente_no_cuenta(self):
        from ejercicios.backfill import puntero_reconstruido
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc, cohorte=self.cohorte, respuesta_raw='p',
            es_correcto=True, aprobado_docente=False,
        )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[0].id)

    def test_todos_resueltos_devuelve_none(self):
        from ejercicios.backfill import puntero_reconstruido
        for ep in self.eps:
            Intento.objects.create(
                estudiante=self.estudiante, ejercicio_practica=ep,
                practica_comision=self.pc, cohorte=self.cohorte, respuesta_raw='p',
                es_correcto=True, aprobado_docente=None,
            )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertIsNone(resultado)

    def test_intento_de_otro_pc_no_cuenta(self):
        from ejercicios.backfill import puntero_reconstruido
        otra_comision = Comision.objects.create(nombre='C-pt-otra')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=otra_comision, cohorte=self.cohorte)
        pc_otro = PracticaComision.objects.create(
            practica=self.practica, comision=otra_comision, orden=1,
        )
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=pc_otro, cohorte=self.cohorte, respuesta_raw='p',
            es_correcto=True, aprobado_docente=None,
        )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[0].id)


class BackfillAtribuirProgresoTests(TestCase):
    """atribuir_progreso(): las tres ramas hoisted desde la migración 0024.

    El esquema real (post-0025/0026) exige ``practica_comision`` NOT NULL y
    ya no tiene el campo ``practica`` en Progreso; el estado "sin resolver"
    que ve el backfill solo existe en el esquema histórico intermedio en el
    que corre la migración. Para probar la función contra los modelos reales,
    cada fila se crea con un pc placeholder válido (para satisfacer la
    constraint) y se le agrega ``practica_id`` como atributo en memoria, sin
    persistirlo, imitando la fila histórica que ve la migración.
    """

    def setUp(self):
        self.docente = _u('doc-bf-atr', es_docente=True)
        self.estudiante = _u('est-bf-atr')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision_a = Comision.objects.create(nombre='C-atr-A')
        self.comision_b = Comision.objects.create(nombre='C-atr-B')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b, cohorte=self.cohorte)
        self.practica = Practica.objects.create(titulo='P-atr', creada_por=self.docente)
        self.pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        self.eps = []
        for i in (1, 2):
            ej = Ejercicio.objects.create(
                enunciado=f'E-atr-{i}', formula_solucion='p',
                tipo='formalizacion', creado_por=self.docente,
            )
            self.eps.append(EjercicioPractica.objects.create(
                practica=self.practica, ejercicio=ej, orden=i,
            ))

    def _progreso_sin_resolver(self, pc_placeholder, ep_actual=None):
        progreso = Progreso.objects.create(
            estudiante=self.estudiante,
            practica_comision=pc_placeholder,
            cohorte=self.cohorte,
            ejercicio_practica_actual=ep_actual,
        )
        progreso.practica_id = self.practica.id
        return progreso

    def test_n1_asigna_el_pc_y_no_toca_el_puntero(self):
        from ejercicios.backfill import atribuir_progreso
        otra_practica = Practica.objects.create(
            titulo='P-atr-otra', creada_por=self.docente,
        )
        otra_pc = PracticaComision.objects.create(
            practica=otra_practica, comision=self.comision_a, orden=2,
        )
        progreso = self._progreso_sin_resolver(otra_pc, ep_actual=self.eps[1])

        resultado = atribuir_progreso(
            Progreso, EjercicioPractica, Intento, progreso, [self.pc_a.id],
        )

        self.assertEqual(resultado, 'n1')
        progreso.refresh_from_db()
        self.assertEqual(progreso.practica_comision_id, self.pc_a.id)
        self.assertEqual(progreso.ejercicio_practica_actual_id, self.eps[1].id)

    def test_n0_borra_la_fila(self):
        from ejercicios.backfill import atribuir_progreso
        progreso = self._progreso_sin_resolver(self.pc_a, ep_actual=self.eps[0])
        pk = progreso.pk

        resultado = atribuir_progreso(
            Progreso, EjercicioPractica, Intento, progreso, [],
        )

        self.assertEqual(resultado, 'n0')
        self.assertFalse(Progreso.objects.filter(pk=pk).exists())

    def test_n2_abre_dos_filas_con_punteros_independientes(self):
        from ejercicios.backfill import atribuir_progreso
        # El estudiante ya resolvió el primer ejercicio, pero solo bajo pc_a.
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_a, cohorte=self.cohorte, respuesta_raw='p',
            es_correcto=True, aprobado_docente=None,
        )
        progreso = self._progreso_sin_resolver(self.pc_a, ep_actual=self.eps[0])

        resultado = atribuir_progreso(
            Progreso, EjercicioPractica, Intento, progreso,
            [self.pc_a.id, self.pc_b.id],
        )

        self.assertEqual(resultado, 'n2')
        filas = Progreso.objects.filter(
            estudiante=self.estudiante,
            practica_comision__in=[self.pc_a, self.pc_b],
        )
        self.assertEqual(filas.count(), 2)

        fila_a = filas.get(practica_comision=self.pc_a)
        fila_b = filas.get(practica_comision=self.pc_b)
        # pc_a: el primer ejercicio ya está resuelto ahí -> apunta al segundo.
        self.assertEqual(fila_a.ejercicio_practica_actual_id, self.eps[1].id)
        # pc_b: sin intentos propios -> apunta al primero, reconstruido aparte.
        self.assertEqual(fila_b.ejercicio_practica_actual_id, self.eps[0].id)


class ProgresoCruzadoEntreComisionesTests(TestCase):
    """Dos comisiones que comparten una Practica canónica no comparten Progreso."""

    def setUp(self):
        self.docente = _u('doc-cruz', es_docente=True)
        self.estudiante = _u('est-cruz')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision_sec = Comision.objects.create(nombre='C-cruz-sec')
        self.comision_libre = Comision.objects.create(nombre='C-cruz-libre')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_sec, cohorte=self.cohorte)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_libre, cohorte=self.cohorte)

        # La MISMA practica canónica en las dos (lo que hace practica_importar).
        self.practica = Practica.objects.create(titulo='P-cruz', creada_por=self.docente)
        self.pc_sec = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_sec, orden=1,
            desbloqueo_secuencial=True,
        )
        self.pc_libre = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_libre, orden=1,
            desbloqueo_secuencial=False,
        )
        self.eps = []
        for i in (1, 2, 3):
            ej = Ejercicio.objects.create(
                enunciado=f'E{i}', formula_solucion='p',
                tipo='formalizacion', creado_por=self.docente,
            )
            self.eps.append(EjercicioPractica.objects.create(
                practica=self.practica, ejercicio=ej, orden=i,
            ))

    def test_hay_una_fila_de_progreso_por_comision(self):
        from ejercicios.progreso import avanzar_progreso
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_sec, cohorte=self.cohorte, respuesta_raw='p', es_correcto=True,
        )
        avanzar_progreso(self.estudiante, self.eps[0], self.pc_sec, self.cohorte)

        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_libre, cohorte=self.cohorte, respuesta_raw='p', es_correcto=True,
        )
        avanzar_progreso(self.estudiante, self.eps[0], self.pc_libre, self.cohorte)

        self.assertEqual(
            Progreso.objects.filter(estudiante=self.estudiante).count(), 2,
        )

    def test_intento_en_la_libre_no_mueve_el_puntero_de_la_secuencial(self):
        from ejercicios.progreso import avanzar_progreso
        # La secuencial arranca en el ejercicio 1.
        Progreso.objects.create(
            estudiante=self.estudiante, cohorte=self.cohorte,
            practica_comision=self.pc_sec, ejercicio_practica_actual=self.eps[0],
        )
        # El estudiante resuelve el TERCERO en la comisión libre.
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[2],
            practica_comision=self.pc_libre, cohorte=self.cohorte, respuesta_raw='p', es_correcto=True,
        )
        avanzar_progreso(self.estudiante, self.eps[2], self.pc_libre, self.cohorte)

        progreso_sec = Progreso.objects.get(
            estudiante=self.estudiante, practica_comision=self.pc_sec,
        )
        self.assertEqual(
            progreso_sec.ejercicio_practica_actual, self.eps[0],
            'la comisión secuencial no debería moverse por un intento de la libre',
        )

    def test_eps_resueltos_no_cuenta_lo_resuelto_en_la_otra_comision(self):
        from ejercicios.progreso import eps_resueltos
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_sec, cohorte=self.cohorte, respuesta_raw='p', es_correcto=True,
        )

        self.assertEqual(eps_resueltos(self.estudiante, self.pc_sec, self.cohorte), {self.eps[0].id})
        self.assertEqual(eps_resueltos(self.estudiante, self.pc_libre, self.cohorte), set())

    def test_esta_resuelto_es_por_comision(self):
        from ejercicios.progreso import esta_resuelto
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_sec, cohorte=self.cohorte, respuesta_raw='p', es_correcto=True,
        )

        self.assertTrue(esta_resuelto(self.estudiante, self.eps[0], self.pc_sec, self.cohorte))
        self.assertFalse(esta_resuelto(self.estudiante, self.eps[0], self.pc_libre, self.cohorte))


class APIPracticaComisionRequeridaTests(TestCase):
    """POST /api/intentos/ exige practica_comision_id y lo valida."""

    def setUp(self):
        self.docente = _u('doc-api-pc', es_docente=True)
        self.estudiante = _u('est-api-pc')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='C-api-pc')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)
        self.practica = Practica.objects.create(titulo='P-api-pc', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )
        ej = Ejercicio.objects.create(
            enunciado='E', formula_solucion='p',
            tipo='formalizacion', creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=self.practica, ejercicio=ej, orden=1,
        )
        self.client.login(username='est-api-pc', password='clave123')

    def test_sin_practica_comision_id_devuelve_400(self):
        resp = self.client.post(
            '/api/intentos/',
            data={'ejercicio_practica_id': self.ep.id, 'respuesta_raw': 'p'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('practica_comision_id', resp.json())

    def test_pc_de_otra_practica_devuelve_400(self):
        otra_practica = Practica.objects.create(titulo='Otra', creada_por=self.docente)
        pc_otra = PracticaComision.objects.create(
            practica=otra_practica, comision=self.comision, orden=2,
        )
        resp = self.client.post(
            '/api/intentos/',
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': pc_otra.id,
                'respuesta_raw': 'p',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_pc_de_comision_ajena_devuelve_403(self):
        otra_comision = Comision.objects.create(nombre='C-ajena')
        pc_ajeno = PracticaComision.objects.create(
            practica=self.practica, comision=otra_comision, orden=1,
        )
        resp = self.client.post(
            '/api/intentos/',
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': pc_ajeno.id,
                'respuesta_raw': 'p',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_pc_valido_guarda_el_intento_con_esa_comision(self):
        resp = self.client.post(
            '/api/intentos/',
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': self.pc.id,
                'respuesta_raw': 'p',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        intento = Intento.objects.get(pk=resp.json()['intento_id'])
        self.assertEqual(intento.practica_comision, self.pc)


class ReadPathAisladoPorComisionTests(TestCase):
    """El estado que ve el estudiante no cruza entre comisiones."""

    def setUp(self):
        self.docente = _u('doc-rp', es_docente=True)
        self.estudiante = _u('est-rp')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision_a = Comision.objects.create(nombre='C-rp-A')
        self.comision_b = Comision.objects.create(nombre='C-rp-B')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b, cohorte=self.cohorte)

        self.practica = Practica.objects.create(titulo='P-rp', creada_por=self.docente)
        self.pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
            desbloqueo_secuencial=False,
        )
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
            desbloqueo_secuencial=False,
        )
        ej = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p',
            tipo='formalizacion', creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=self.practica, ejercicio=ej, orden=1,
        )
        # Resuelto SOLO en la comisión A.
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc_a, cohorte=self.cohorte, respuesta_raw='p',
            es_correcto=True, aprobado_docente=True,
        )
        self.client.login(username='est-rp', password='clave123')

    def test_practica_detail_en_B_no_muestra_el_ejercicio_como_aprobado(self):
        resp = self.client.get(reverse('ejercicios:practica', args=[self.pc_b.id]))
        estados = [d['estado'] for d in resp.context['eps_data']]
        self.assertEqual(estados, ['actual'])

    def test_practica_detail_en_A_si_lo_muestra_aprobado(self):
        resp = self.client.get(reverse('ejercicios:practica', args=[self.pc_a.id]))
        estados = [d['estado'] for d in resp.context['eps_data']]
        self.assertEqual(estados, ['aprobado'])

    def test_ejercicio_detail_en_B_deja_enviar(self):
        resp = self.client.get(
            reverse('ejercicios:ejercicio', args=[self.pc_b.id, self.ep.id])
        )
        self.assertTrue(resp.context['puede_enviar'])

    def test_ejercicio_detail_en_A_no_deja_reenviar(self):
        resp = self.client.get(
            reverse('ejercicios:ejercicio', args=[self.pc_a.id, self.ep.id])
        )
        self.assertFalse(resp.context['puede_enviar'])

    def test_home_marca_completa_solo_la_comision_donde_se_completo(self):
        from ejercicios.progreso import avanzar_progreso
        avanzar_progreso(self.estudiante, self.ep, self.pc_a, self.cohorte)

        resp = self.client.get(reverse('ejercicios:home'))
        estados = {}
        for cd in resp.context['comisiones_data']:
            for pd in cd['practicas']:
                estados[pd['pc'].id] = pd['estado']

        self.assertEqual(estados[self.pc_a.id], 'completa')
        self.assertIsNone(estados[self.pc_b.id])


class BackfillReatribuirIntentoTests(TestCase):
    """reatribuir_intento(): corrige lo que la 0015 atribuyó a ciegas."""

    def setUp(self):
        self.docente = _u('doc-bf-reat', es_docente=True)
        self.estudiante = _u('est-bf-reat')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision_a = Comision.objects.create(nombre='C-reat-A')
        self.comision_b = Comision.objects.create(nombre='C-reat-B')
        self.practica = Practica.objects.create(titulo='P-reat', creada_por=self.docente)
        self.pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )

    def _indices(self):
        from ejercicios.backfill import construir_indices
        return construir_indices(PracticaComision, Inscripcion)

    def _reatribuir(self, pc_actual):
        from ejercicios.backfill import reatribuir_intento
        pcs_por_practica, comisiones_por_estudiante = self._indices()
        return reatribuir_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id, pc_actual.id,
        )

    def test_atribucion_coherente_no_se_toca(self):
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)

        self.assertIsNone(self._reatribuir(self.pc_a))

    def test_atribuido_a_una_comision_ajena_se_corrige(self):
        # Cursa en A, pero la 0015 lo dejó apuntando a B.
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)

        self.assertEqual(self._reatribuir(self.pc_b), self.pc_a.id)

    def test_desinscripto_se_deja_como_esta(self):
        # Sin inscripción no hay con qué reemplazar: anular la FK rompería la 0026.
        self.assertIsNone(self._reatribuir(self.pc_b))

    def test_ambiguo_se_deja_como_esta(self):
        # Inscripto en ambas: no hay un único candidato, no se adivina.
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=self.cohorte)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b, cohorte=self.cohorte)


class RecursanteAisladoTests(TestCase):
    """Lo resuelto en una cohorte no cuenta como resuelto en la siguiente."""

    def setUp(self):
        from cursos.models import Cohorte, Comision, Inscripcion
        from ejercicios.models import Ejercicio, EjercicioPractica, Practica, PracticaComision

        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.est = _u('recursa-progreso')
        self.comision = Comision.objects.create(nombre='IPC Noche')
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c1)

        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)

    def test_intento_correcto_de_c1_no_cuenta_en_c2(self):
        from ejercicios.models import Intento
        from ejercicios.progreso import esta_resuelto

        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c1, respuesta_raw='p', es_correcto=True,
        )
        self.assertTrue(esta_resuelto(self.est, self.ep, self.pc, self.c1))
        self.assertFalse(esta_resuelto(self.est, self.ep, self.pc, self.c2))

    def test_eps_resueltos_acota_por_cohorte(self):
        from ejercicios.models import Intento
        from ejercicios.progreso import eps_resueltos

        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c1, respuesta_raw='p', es_correcto=True,
        )
        self.assertEqual(eps_resueltos(self.est, self.pc, self.c1), {self.ep.pk})
        self.assertEqual(eps_resueltos(self.est, self.pc, self.c2), set())

    def test_avanzar_progreso_crea_fila_por_cohorte(self):
        from ejercicios.models import Intento, Progreso
        from ejercicios.progreso import avanzar_progreso

        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c1, respuesta_raw='p', es_correcto=True,
        )
        avanzar_progreso(self.est, self.ep, self.pc, self.c1)
        avanzar_progreso(self.est, self.ep, self.pc, self.c2)

        self.assertEqual(
            Progreso.objects.filter(estudiante=self.est, practica_comision=self.pc).count(), 2,
        )


class ProgresoClavePorCohorteTests(TestCase):
    """El progreso es por terna (estudiante, practica_comision, cohorte)."""

    def setUp(self):
        from cursos.models import Cohorte, Comision, Inscripcion
        from ejercicios.models import Ejercicio, EjercicioPractica, Practica, PracticaComision

        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.est = _u('recursante')
        self.comision = Comision.objects.create(nombre='IPC Noche')
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c1)
        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)

    def test_acepta_mismo_par_en_dos_cohortes(self):
        from ejercicios.models import Progreso
        Progreso.objects.create(estudiante=self.est, practica_comision=self.pc, cohorte=self.c1)
        Progreso.objects.create(estudiante=self.est, practica_comision=self.pc, cohorte=self.c2)
        self.assertEqual(Progreso.objects.filter(estudiante=self.est).count(), 2)

    def test_rechaza_duplicado_dentro_de_una_cohorte(self):
        from django.db import IntegrityError, transaction
        from ejercicios.models import Progreso
        Progreso.objects.create(estudiante=self.est, practica_comision=self.pc, cohorte=self.c1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Progreso.objects.create(estudiante=self.est, practica_comision=self.pc, cohorte=self.c1)


class RecursanteReadPathTests(TestCase):
    """Code review (Hallazgo 1): el read path del estudiante (home,
    practica_detail, ejercicio_detail) debe usar la cohorte del estudiante en
    cada comisión. Un recursante con Progreso en dos cohortes para el mismo
    practica_comision no debe hacer crashear estas tres vistas, y el estado
    que ven debe corresponder a SU cohorte actual (la de su inscripción más
    reciente), no a una fila arbitraria."""

    def setUp(self):
        self.docente = _u('doc-recursa-read', es_docente=True)
        self.estudiante = _u('est-recursa-read')

        # Los ids de Cohorte se crean deliberadamente al REVÉS del orden
        # cronológico real (cohorte_actual con id más bajo, cohorte_vieja con
        # id más alto). cohorte_de() se basa en la fecha de inscripción, no en
        # el id de la cohorte, así que esto no debería importar para un código
        # correcto — pero si un query sin filtro de cohorte cae por accidente
        # en "el último por id/inserción gana", este orden invertido lo
        # expone en vez de taparlo.
        self.cohorte_actual = Cohorte.objects.create(anio=2030, cuatrimestre=1)
        self.cohorte_vieja = Cohorte.objects.create(anio=2020, cuatrimestre=1)

        self.comision = Comision.objects.create(nombre='IPC Recursa Read')
        # Inscripción vieja primero, luego la de la camada en la que recursa:
        # cohorte_de() debe resolver a cohorte_actual, la más reciente.
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_vieja,
        )
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_actual,
        )

        practica = Practica.objects.create(titulo='P-recursa-read', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1, desbloqueo_secuencial=True,
        )
        ej1 = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        ej2 = Ejercicio.objects.create(
            enunciado='E2', formula_solucion='q', tipo='formalizacion', creado_por=self.docente,
        )
        self.ep1 = EjercicioPractica.objects.create(practica=practica, ejercicio=ej1, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=practica, ejercicio=ej2, orden=2)

        # Progreso de la camada VIEJA: completó la práctica entera.
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep1, practica_comision=self.pc,
            cohorte=self.cohorte_vieja, respuesta_raw='p', es_correcto=True, aprobado_docente=True,
        )
        Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte_vieja,
            ejercicio_practica_actual=None,
        )

        # Progreso de la camada ACTUAL: recién arranca, sin intentos.
        Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte_actual,
            ejercicio_practica_actual=self.ep1,
        )

        self.client.login(username='est-recursa-read', password='clave123')

    def test_practica_detail_no_revienta_y_usa_la_cohorte_actual(self):
        resp = self.client.get(reverse('ejercicios:practica', args=[self.pc.id]))

        self.assertEqual(resp.status_code, 200)
        estados = [d['estado'] for d in resp.context['eps_data']]
        # En la cohorte actual no hay intentos todavía: ep1 es el actual y
        # ep2 sigue bloqueado. Si mezclara con la vieja vería ep1 aprobado.
        self.assertEqual(estados, ['actual', 'bloqueado'])

    def test_ejercicio_detail_no_revienta_y_usa_la_cohorte_actual(self):
        resp = self.client.get(reverse('ejercicios:ejercicio', args=[self.pc.id, self.ep1.id]))

        self.assertEqual(resp.status_code, 200)
        # En la cohorte actual el estudiante puede enviar: no hay intento
        # todavía. Si mezclara con la vieja (ya resuelto) no lo dejaría.
        self.assertTrue(resp.context['puede_enviar'])

    def test_home_no_revienta_y_muestra_el_estado_de_la_cohorte_actual(self):
        resp = self.client.get(reverse('ejercicios:home'))

        self.assertEqual(resp.status_code, 200)
        estados = {}
        for cd in resp.context['comisiones_data']:
            for pd in cd['practicas']:
                estados[pd['pc'].id] = pd['estado']
        # El progreso de la cohorte actual del estudiante está en curso, no
        # completo: si el dict se quedara con la fila de la cohorte vieja por
        # azar de iteración, este assert fallaría con 'completa'.
        self.assertEqual(estados[self.pc.id], 'en_curso')

    def test_historial_vacio_y_sin_precarga_si_el_intento_es_de_la_camada_vieja(self):
        # El único intento sobre ep1 es el de cohorte_vieja que crea setUp.
        resp = self.client.get(reverse('ejercicios:ejercicio', args=[self.pc.id, self.ep1.id]))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.context['intentos']), [])
        self.assertIsNone(resp.context['ultimo_intento'])
        # Sin filtro de cohorte, ultimo_intento sería el de la camada vieja y,
        # como en esta camada puede enviar, el formulario arrancaría precargado
        # con aquella respuesta ('p') y su diccionario.
        self.assertTrue(resp.context['puede_enviar'])
        self.assertEqual(json.loads(resp.context['initial_formula_json']), '')
        self.assertEqual(json.loads(resp.context['initial_diccionario_json']), {})

    def test_historial_y_precarga_toman_el_intento_de_la_cohorte_actual(self):
        intento_actual = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep1, practica_comision=self.pc,
            cohorte=self.cohorte_actual, respuesta_raw='r', es_correcto=False,
            diccionario={'r': 'llueve'},
        )

        resp = self.client.get(reverse('ejercicios:ejercicio', args=[self.pc.id, self.ep1.id]))

        self.assertEqual(resp.status_code, 200)
        # El de la camada vieja queda afuera; el de esta camada, adentro.
        self.assertEqual([i.pk for i in resp.context['intentos']], [intento_actual.pk])
        self.assertEqual(resp.context['ultimo_intento'].pk, intento_actual.pk)
        self.assertEqual(json.loads(resp.context['initial_formula_json']), 'r')
        self.assertEqual(json.loads(resp.context['initial_diccionario_json']), {'r': 'llueve'})


class HomeRecursanteNoDuplicaComisionTests(TestCase):
    """Code review (Important I4): Comision.objects.filter(estudiantes=usuario)
    hace join contra Inscripcion (M2M por tabla intermedia). Un recursante
    tiene dos Inscripcion en la misma comisión (una por cohorte), así que sin
    .distinct() el join devuelve la Comision duplicada y home() muestra dos
    tarjetas de la misma comisión."""

    def setUp(self):
        self.docente = _u('doc-recursa-home', es_docente=True)
        self.estudiante = _u('est-recursa-home')

        self.cohorte_vieja = Cohorte.objects.create(anio=2020, cuatrimestre=1)
        self.cohorte_actual = Cohorte.objects.get(anio=2026, cuatrimestre=1)

        self.comision = Comision.objects.create(nombre='IPC Recursa Home')
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_vieja,
        )
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_actual,
        )

        self.client.login(username='est-recursa-home', password='clave123')

    def test_home_no_duplica_la_comision_del_recursante(self):
        resp = self.client.get(reverse('ejercicios:home'))

        self.assertEqual(resp.status_code, 200)
        ids = [cd['comision'].id for cd in resp.context['comisiones_data']]
        self.assertEqual(ids, [self.comision.id])


class ReconciliarProgresoAprobacionesCommandTests(TestCase):
    """Code review (Hallazgo 2): el comando debe poder CREAR un Progreso sin
    reventar por el NOT NULL de cohorte cuando no existe todavía una fila."""

    def setUp(self):
        self.docente = _u('doc-reconc-prog', es_docente=True)
        self.estudiante = _u('est-reconc-prog')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Reconc')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte)

        self.practica = Practica.objects.create(titulo='P-reconc', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)
        ej1 = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        ej2 = Ejercicio.objects.create(
            enunciado='E2', formula_solucion='q', tipo='formalizacion', creado_por=self.docente,
        )
        self.ep1 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej1, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej2, orden=2)

        # Intento incorrecto aprobado a mano por el docente, sin que exista
        # todavía un Progreso para este (estudiante, practica_comision): el
        # comando tiene que crearlo.
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep1, practica_comision=self.pc,
            cohorte=self.cohorte, respuesta_raw='x', es_correcto=False, aprobado_docente=True,
        )

    def test_crea_progreso_con_cohorte_sin_reventar(self):
        self.assertFalse(Progreso.objects.filter(estudiante=self.estudiante, practica_comision=self.pc).exists())

        stdout = StringIO()
        call_command('reconciliar_progreso_aprobaciones', stdout=stdout)

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica_comision=self.pc)
        self.assertEqual(progreso.cohorte, self.cohorte)
        # ep1 aprobado por el docente: el progreso avanza al siguiente.
        self.assertEqual(progreso.ejercicio_practica_actual, self.ep2)


class GateFechasPorCohorteTests(TestCase):
    """`fecha_apertura`/`fecha_cierre` viven en PracticaComision, compartida
    entre cohortes. El gate de disponibilidad solo debe aplicar a la cohorte
    activa: quien es de una camada anterior sigue practicando para rendir el
    final sin que el calendario de la cursada nueva lo deje afuera."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone

        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        Cohorte.objects.filter(pk=self.c1.pk).update(activa=False)
        Cohorte.objects.filter(pk=self.c2.pk).update(activa=True)

        self.comision = Comision.objects.create(nombre='IPC Noche')
        self.est_vieja = _u('final-c1')
        self.est_actual = _u('cursa-c2')
        Inscripcion.objects.create(estudiante=self.est_vieja, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est_actual, comision=self.comision, cohorte=self.c2)

        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
            fecha_cierre=timezone.now() - timedelta(days=1),
        )
        self.url = reverse('ejercicios:practica', args=[self.pc.pk])

    def test_camada_vieja_entra_aunque_este_cerrada(self):
        self.client.login(username='final-c1', password='clave123')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Práctica cerrada')

    def test_cohorte_activa_si_queda_afuera(self):
        self.client.login(username='cursa-c2', password='clave123')
        resp = self.client.get(self.url)
        self.assertContains(resp, 'cerrada')

    def test_camada_vieja_sigue_viendo_el_aula_en_home(self):
        """`home` no filtra por cohorte: quien tiene inscripción ve su comisión."""
        self.client.login(username='final-c1', password='clave123')
        resp = self.client.get(reverse('ejercicios:home'))
        self.assertContains(resp, 'IPC Noche')

    def test_ejercicio_detail_tambien_deja_entrar_a_la_camada_vieja(self):
        """El gate está duplicado en las dos vistas: hay que cubrir las dos."""
        ep = EjercicioPractica.objects.get(practica=self.pc.practica)
        url = reverse('ejercicios:ejercicio', args=[self.pc.pk, ep.pk])

        self.client.login(username='final-c1', password='clave123')
        vieja = self.client.get(url)
        self.assertEqual(vieja.status_code, 200)
        self.assertNotContains(vieja, 'Práctica cerrada')

        self.client.login(username='cursa-c2', password='clave123')
        actual = self.client.get(url)
        self.assertContains(actual, 'Práctica cerrada')


class HistorialUnificadoTests(TestCase):
    """El historial propio del estudiante y el del docente salen del mismo
    helper, asi que el estudiante ve su intento de determinacion_verdad con
    el mismo enriquecido que ve el docente (diccionario_con_valores)."""

    def setUp(self):
        self.docente = _u('doc-hist-unif', es_docente=True)
        self.estudiante = _u('est-hist-unif')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Unif')
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte,
        )

        practica = Practica.objects.create(titulo='P-unif', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
        )
        ejercicio = Ejercicio.objects.create(
            enunciado='Determinar', formula_solucion='p', tipo='determinacion_verdad',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=practica, ejercicio=ejercicio, orden=1,
        )
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=self.cohorte,
            respuesta_raw='p', es_correcto=True,
            diccionario={'p': 'llueve'}, valores_verdad={'p': True},
        )
        self.client.login(username='est-hist-unif', password='clave123')

    def test_vista_propia_enriquece_determinacion_verdad(self):
        resp = self.client.get(reverse('ejercicios:mi_historial'))

        self.assertEqual(resp.status_code, 200)
        grupo = resp.context['historial_por_cohorte'][0]['grupos'][0]
        self.assertEqual(
            grupo['ultimo_intento'].diccionario_con_valores,
            [{'letra': 'p', 'frase': 'llueve', 'valor': True}],
        )


class HistorialPorCohorteTests(TestCase):
    """El historial separa las camadas: un recursante con intentos del mismo
    ejercicio en dos cohortes ve dos grupos, no uno con todo mezclado."""

    def setUp(self):
        self.docente = _u('doc-hist-coh', es_docente=True)
        self.estudiante = _u('est-hist-coh')

        # Ids al reves del orden cronologico real, como en
        # RecursanteReadPathTests: si algun query cae en "el ultimo por id
        # gana", este orden lo expone en vez de taparlo.
        self.cohorte_actual = Cohorte.objects.create(anio=2030, cuatrimestre=1)
        self.cohorte_vieja = Cohorte.objects.create(anio=2020, cuatrimestre=1)

        self.comision = Comision.objects.create(nombre='IPC Hist Coh')
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_vieja,
        )
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_actual,
        )

        practica = Practica.objects.create(titulo='P-hist-coh', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
        )
        ejercicio = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p', tipo='formalizacion',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=practica, ejercicio=ejercicio, orden=1,
        )

        self.intento_viejo = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=self.cohorte_vieja,
            respuesta_raw='p', es_correcto=True,
        )
        self.intento_nuevo = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=self.cohorte_actual,
            respuesta_raw='q', es_correcto=False,
        )
        self.client.login(username='est-hist-coh', password='clave123')

    def test_dos_camadas_dan_dos_secciones_la_reciente_primero(self):
        resp = self.client.get(reverse('ejercicios:mi_historial'))

        self.assertEqual(resp.status_code, 200)
        secciones = resp.context['historial_por_cohorte']
        self.assertEqual(
            [s['cohorte'].pk for s in secciones],
            [self.cohorte_actual.pk, self.cohorte_vieja.pk],
        )

    def test_cada_seccion_lleva_el_ultimo_intento_de_su_cohorte(self):
        resp = self.client.get(reverse('ejercicios:mi_historial'))

        secciones = resp.context['historial_por_cohorte']
        # Un grupo por seccion: el mismo ejercicio, pero camadas distintas.
        # Sin el cambio de clave los dos intentos caerian en un unico grupo.
        self.assertEqual([len(s['grupos']) for s in secciones], [1, 1])
        self.assertEqual(
            secciones[0]['grupos'][0]['ultimo_intento'].pk, self.intento_nuevo.pk,
        )
        self.assertEqual(
            secciones[1]['grupos'][0]['ultimo_intento'].pk, self.intento_viejo.pk,
        )
        # Y ninguno arrastra al otro como "intento anterior".
        self.assertEqual(secciones[0]['grupos'][0]['intentos_anteriores'], [])
        self.assertEqual(secciones[1]['grupos'][0]['intentos_anteriores'], [])

    def test_una_sola_cohorte_igual_da_su_seccion(self):
        otro = _u('est-una-camada')
        Inscripcion.objects.create(
            estudiante=otro, comision=self.comision, cohorte=self.cohorte_actual,
        )
        Intento.objects.create(
            estudiante=otro, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.cohorte_actual, respuesta_raw='p', es_correcto=True,
        )
        self.client.login(username='est-una-camada', password='clave123')

        resp = self.client.get(reverse('ejercicios:mi_historial'))

        secciones = resp.context['historial_por_cohorte']
        self.assertEqual(len(secciones), 1)
        self.assertEqual(secciones[0]['cohorte'].pk, self.cohorte_actual.pk)

    def test_el_encabezado_de_camada_se_renderiza(self):
        resp = self.client.get(reverse('ejercicios:mi_historial'))

        self.assertContains(resp, '2030 – C1')
        self.assertContains(resp, '2020 – C1')


# ─── Deuda de tests I6: los tres commands ciegos a la cohorte (569b6d4) ──────
#
# Patrón común: un mismo estudiante con dos Inscripcion (y dos Progreso) en
# la misma comisión, una por cohorte. Se corrige un intento de la cohorte
# ACTUAL; se verifica que el comando avanza únicamente el Progreso de esa
# cohorte y deja intacto el de la cohorte VIEJA (que se queda bloqueada en el
# mismo ejercicio, sin ningún intento que la justifique avanzar). Antes del
# fix de 569b6d4, `_avanzar_progreso`/`_reconciliar_progreso` resolvían el
# Progreso con `.filter(estudiante_id, practica_comision_id).first()` sin
# `cohorte_id`, así que el primer Progreso por orden de creación (acá, el de
# la cohorte vieja) es el que se llevaría el avance en vez del correcto.

class ReconciliarVMayusculaCommandTests(TestCase):
    """`reconciliar_V_mayuscula` debe resolver el Progreso de la cohorte del
    propio Intento, no una fila arbitraria, cuando el estudiante recursa."""

    def setUp(self):
        self.docente = _u('doc-vmay-rec', es_docente=True)
        self.estudiante = _u('est-vmay-rec')

        self.cohorte_vieja = Cohorte.objects.create(anio=2020, cuatrimestre=1)
        self.cohorte_actual = Cohorte.objects.get(anio=2026, cuatrimestre=1)

        self.comision = Comision.objects.create(nombre='IPC VMay Recursa')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_vieja)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_actual)

        self.practica = Practica.objects.create(titulo='P-vmay-rec')
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)
        ej1 = Ejercicio.objects.create(
            enunciado='xor', formula_solucion='(J∨M).~(J.M)', tipo='formalizacion', creado_por=self.docente,
        )
        ej2 = Ejercicio.objects.create(
            enunciado='E2', formula_solucion='q', tipo='formalizacion', creado_por=self.docente,
        )
        self.ep1 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej1, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej2, orden=2)

        # Progreso de la cohorte VIEJA creado primero (pk más bajo): sin
        # filtro de cohorte, .first() lo agarraría a él.
        self.progreso_vieja = Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte_vieja,
            ejercicio_practica_actual=self.ep1,
        )
        self.progreso_actual = Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte_actual,
            ejercicio_practica_actual=self.ep1,
        )

        # Único intento afectado por el bug de "V" mayúscula: de la cohorte ACTUAL.
        self.intento = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep1, practica_comision=self.pc,
            cohorte=self.cohorte_actual, respuesta_raw='(JvM).~(J.M)', es_correcto=False,
        )

    def test_avanza_solo_el_progreso_de_la_cohorte_del_intento(self):
        call_command('reconciliar_V_mayuscula')

        self.intento.refresh_from_db()
        self.assertTrue(self.intento.es_correcto)

        self.progreso_actual.refresh_from_db()
        self.progreso_vieja.refresh_from_db()
        self.assertEqual(self.progreso_actual.ejercicio_practica_actual, self.ep2)
        # La cohorte vieja no tiene ningún intento corregido: debe seguir
        # bloqueada en ep1, no arrastrada por el avance de la otra camada.
        self.assertEqual(self.progreso_vieja.ejercicio_practica_actual, self.ep1)

    def test_dry_run_no_toca_ningun_progreso(self):
        call_command('reconciliar_V_mayuscula', dry_run=True)

        self.intento.refresh_from_db()
        self.progreso_actual.refresh_from_db()
        self.progreso_vieja.refresh_from_db()
        self.assertFalse(self.intento.es_correcto)
        self.assertEqual(self.progreso_actual.ejercicio_practica_actual, self.ep1)
        self.assertEqual(self.progreso_vieja.ejercicio_practica_actual, self.ep1)


class CorregirEjercicioJuicioCommandTests(TestCase):
    """`corregir_ejercicio_juicio --ejercicio-id` debe resolver el Progreso
    de la cohorte del propio Intento, no una fila arbitraria."""

    def setUp(self):
        self.docente = _u('doc-corr-juicio-rec', es_docente=True)
        self.estudiante = _u('est-corr-juicio-rec')

        self.cohorte_vieja = Cohorte.objects.create(anio=2020, cuatrimestre=1)
        self.cohorte_actual = Cohorte.objects.get(anio=2026, cuatrimestre=1)

        self.comision = Comision.objects.create(nombre='IPC Juicio Recursa')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_vieja)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_actual)

        self.practica = Practica.objects.create(titulo='P-corr-juicio-rec')
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)

        self.solucion = [
            {'formula': 'P->(R&D)', 'tipo': 'premisa'},
            {'formula': '~D&R', 'tipo': 'premisa'},
            {'formula': 'P', 'tipo': 'conclusion'},
        ]
        self.argumento_estudiante = [
            {'formula': 'E->(R&D)', 'tipo': 'premisa'},
            {'formula': '~D&R', 'tipo': 'premisa'},
            {'formula': 'E', 'tipo': 'conclusion'},
        ]
        self.ejercicio = Ejercicio.objects.create(
            enunciado='Argumento con renombramiento', formula_solucion=json.dumps(self.solucion),
            tipo='tabla_verdad', creado_por=self.docente,
        )
        ej_siguiente = Ejercicio.objects.create(
            enunciado='Siguiente', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        self.ep1 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=self.ejercicio, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej_siguiente, orden=2)

        self.progreso_vieja = Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte_vieja,
            ejercicio_practica_actual=self.ep1,
        )
        self.progreso_actual = Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte_actual,
            ejercicio_practica_actual=self.ep1,
        )

        from motor import verificar_argumento
        tabla_estudiante = verificar_argumento(
            self.argumento_estudiante, self.argumento_estudiante, False,
        )['tabla_canonica']
        self.intento = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep1, practica_comision=self.pc,
            cohorte=self.cohorte_actual, respuesta_raw=json.dumps(self.argumento_estudiante),
            es_correcto=False, tabla_json=tabla_estudiante, juicio_estudiante=False,
        )

    def test_avanza_solo_el_progreso_de_la_cohorte_del_intento(self):
        call_command('corregir_ejercicio_juicio', ejercicio_id=self.ejercicio.id)

        self.intento.refresh_from_db()
        self.assertTrue(self.intento.es_correcto)

        self.progreso_actual.refresh_from_db()
        self.progreso_vieja.refresh_from_db()
        self.assertEqual(self.progreso_actual.ejercicio_practica_actual, self.ep2)
        self.assertEqual(self.progreso_vieja.ejercicio_practica_actual, self.ep1)

    def test_dry_run_no_toca_ningun_progreso(self):
        call_command('corregir_ejercicio_juicio', ejercicio_id=self.ejercicio.id, dry_run=True)

        self.intento.refresh_from_db()
        self.progreso_actual.refresh_from_db()
        self.progreso_vieja.refresh_from_db()
        self.assertFalse(self.intento.es_correcto)
        self.assertEqual(self.progreso_actual.ejercicio_practica_actual, self.ep1)
        self.assertEqual(self.progreso_vieja.ejercicio_practica_actual, self.ep1)


class RecorregirTablaVerdadCommandTests(TestCase):
    """`recorregir_tabla_verdad` debe resolver el Progreso de la cohorte del
    propio Intento, no una fila arbitraria."""

    def setUp(self):
        self.docente = _u('doc-recorr-tv-rec', es_docente=True)
        self.estudiante = _u('est-recorr-tv-rec')

        self.cohorte_vieja = Cohorte.objects.create(anio=2020, cuatrimestre=1)
        self.cohorte_actual = Cohorte.objects.get(anio=2026, cuatrimestre=1)

        self.comision = Comision.objects.create(nombre='IPC Recorr TV Recursa')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_vieja)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_actual)

        self.practica = Practica.objects.create(titulo='P-recorr-tv-rec')
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)

        self.solucion = [
            {'formula': 'P->(R&D)', 'tipo': 'premisa'},
            {'formula': '~D&R', 'tipo': 'premisa'},
            {'formula': 'P', 'tipo': 'conclusion'},
        ]
        self.argumento_estudiante = [
            {'formula': 'E->(R&D)', 'tipo': 'premisa'},
            {'formula': '~D&R', 'tipo': 'premisa'},
            {'formula': 'E', 'tipo': 'conclusion'},
        ]
        ejercicio = Ejercicio.objects.create(
            enunciado='Argumento con renombramiento', formula_solucion=json.dumps(self.solucion),
            tipo='tabla_verdad', creado_por=self.docente,
        )
        ej_siguiente = Ejercicio.objects.create(
            enunciado='Siguiente', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        self.ep1 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ejercicio, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej_siguiente, orden=2)

        self.progreso_vieja = Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte_vieja,
            ejercicio_practica_actual=self.ep1,
        )
        self.progreso_actual = Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.cohorte_actual,
            ejercicio_practica_actual=self.ep1,
        )

        from motor import verificar_argumento
        tabla_estudiante = verificar_argumento(
            self.argumento_estudiante, self.argumento_estudiante, False,
        )['tabla_canonica']
        self.intento = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep1, practica_comision=self.pc,
            cohorte=self.cohorte_actual, respuesta_raw=json.dumps(self.argumento_estudiante),
            es_correcto=False, tabla_json=tabla_estudiante, juicio_estudiante=False,
        )

    def test_avanza_solo_el_progreso_de_la_cohorte_del_intento(self):
        call_command('recorregir_tabla_verdad')

        self.intento.refresh_from_db()
        self.assertTrue(self.intento.es_correcto)

        self.progreso_actual.refresh_from_db()
        self.progreso_vieja.refresh_from_db()
        self.assertEqual(self.progreso_actual.ejercicio_practica_actual, self.ep2)
        self.assertEqual(self.progreso_vieja.ejercicio_practica_actual, self.ep1)

    def test_dry_run_no_toca_ningun_progreso(self):
        call_command('recorregir_tabla_verdad', dry_run=True)

        self.intento.refresh_from_db()
        self.progreso_actual.refresh_from_db()
        self.progreso_vieja.refresh_from_db()
        self.assertFalse(self.intento.es_correcto)
        self.assertEqual(self.progreso_actual.ejercicio_practica_actual, self.ep1)
        self.assertEqual(self.progreso_vieja.ejercicio_practica_actual, self.ep1)
