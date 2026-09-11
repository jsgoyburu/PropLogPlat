from django.test import TestCase, Client
from django.urls import reverse

from .models import Intento, Progreso
from .tests import _u


class ExperimentacionTests(TestCase):
    def setUp(self):
        self.url = reverse('ejercicios:experimentacion')
        self.user = _u('explora', debe_cambiar_password=False)
        self.client.force_login(self.user)

    def calcular(self, formula, accion='tabla'):
        return self.client.post(self.url, {'formula': formula, 'accion': accion})

    def test_acceso_todos_los_roles_sin_comision(self):
        for flags in ({}, {'es_docente': True}, {'is_staff': True}):
            for name, value in flags.items():
                setattr(self.user, name, value)
            self.user.save()
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, self.url)
            self.assertEqual(self.calcular('p').status_code, 200)

    def test_requiere_login_y_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {'formula': 'p'}).status_code, 403)

    def test_tabla_orden_escrito_y_condicional(self):
        response = self.calcular('q -> p')
        self.assertEqual(response.context['variables'], ['q', 'p'])
        self.assertEqual(response.context['filas'], [
            [True, True, True], [True, False, False],
            [False, True, True], [False, False, True],
        ])
        self.assertEqual(response.context['clasificacion'], 'Contingencia')

    def test_simplificacion_conserva_variables_y_clasificacion(self):
        for formula, clasificacion in [('p ≡ p', 'Tautología'), ('p . ~p', 'Contradicción')]:
            response = self.calcular(formula)
            self.assertEqual(response.context['variables'], ['p'])
            self.assertEqual(len(response.context['filas']), 2)
            self.assertEqual(response.context['clasificacion'], clasificacion)

    def test_variable_resultado_no_colisiona(self):
        response = self.calcular('~resultado')
        self.assertEqual(response.context['filas'], [[True, False], [False, True]])

    def test_validar_sin_generar_tabla(self):
        response = self.calcular('(p ⊃ q) ≡ (~p ∨ q)', 'validar')
        self.assertTrue(response.context['valida'])
        self.assertNotIn('filas', response.context)

    def test_errores_sin_resultados_y_conserva_entrada(self):
        for formula in ['', 'p · q ∨ r', 'p &', '(p', 'p)', ')(', 'p · q · r', '<script>']:
            response = self.calcular(formula)
            self.assertTrue(response.context['form'].errors)
            self.assertNotIn('filas', response.context)
            self.assertEqual(response.context['form']['formula'].value(), formula)

    def test_limites_antes_de_evaluar(self):
        for formula in ['p' * 501, 'p ⊃ q ⊃ r ⊃ s ⊃ t ⊃ u ⊃ w ⊃ x ⊃ y', '(' * 240 + 'p' + ')' * 240]:
            response = self.calcular(formula)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        response = self.calcular('p ⊃ (q ⊃ (r ⊃ (s ⊃ (t ⊃ (u ⊃ (w ⊃ x))))))')
        self.assertEqual(len(response.context['filas']), 256)

    def test_no_crea_intentos_ni_progreso(self):
        before = (Intento.objects.count(), Progreso.objects.count())
        self.calcular('p ⊃ q')
        self.calcular('p &')
        self.assertEqual((Intento.objects.count(), Progreso.objects.count()), before)

    def argumento(self, premisas, conclusion):
        return self.client.post(self.url, {'modo': 'argumento', 'premisas': premisas, 'conclusion': conclusion})

    def test_obf_explicita(self):
        self.assertContains(self.calcular('p', 'validar'), 'Es una oración bien formada (OBF).')
        self.assertContains(self.calcular('p &', 'validar'), 'No es una oración bien formada (OBF).')
        self.assertNotContains(self.calcular('p' * 501), 'No es una oración bien formada')

    def test_argumento_exige_premisa_y_conclusion(self):
        for premisas, conclusion in [('', 'p'), ('p', ''), ('p', 'p &'), ('p\nq)', 'q')]:
            response = self.argumento(premisas, conclusion)
            self.assertTrue(response.context['form'].errors)
            self.assertNotIn('argumento', response.context)

    def test_modus_ponens_contradiccion_prueba_pero_premisas_compatibles(self):
        result = self.argumento('p ⊃ q\np', 'q').context['argumento']
        self.assertFalse(result['contradiccion_premisas'])
        self.assertTrue(result['contradiccion_prueba'])
        self.assertEqual(result['contraejemplos'], 0)
        self.assertEqual(len(result['filas']), 4)

    def test_afirmacion_consecuente_contraejemplo_visible(self):
        response = self.argumento('p -> q\nq', 'p')
        result = response.context['argumento']
        self.assertFalse(result['contradiccion_prueba'])
        self.assertEqual(result['contraejemplos'], 1)
        fila = next(f for f in result['filas'] if f['contraejemplo'])
        self.assertEqual(fila['valores'], [False, True, True, True, False, True, True])
        self.assertContains(response, 'Contraejemplos')

    def test_premisas_inconsistentes_validez_vacua(self):
        response = self.argumento('p\n~p', 'q')
        self.assertTrue(response.context['argumento']['contradiccion_premisas'])
        self.assertTrue(response.context['argumento']['contradiccion_prueba'])
        self.assertContains(response, 'vacuidad')

    def test_una_premisa_y_variables_de_conclusion(self):
        result = self.argumento('q', 'p').context['argumento']
        self.assertEqual(result['variables'], ['q', 'p'])
        self.assertEqual(result['contraejemplos'], 1)
        result = self.argumento('p', '~p').context['argumento']
        self.assertFalse(result['contradiccion_prueba'])
        # P ∧ C sería contradictoria, pero la prueba correcta usa P ∧ ¬C.
        self.assertFalse(result['contradiccion_premisas'])

    def test_limites_argumento(self):
        for premisas, conclusion in [('p\n' * 9, 'p'), ('p' * 501, 'p'),
                                     ('p\nq\nr\ns\nt\nu\nw\nx', 'y')]:
            response = self.argumento(premisas, conclusion)
            self.assertTrue(response.context['form'].errors)
            self.assertNotIn('argumento', response.context)

    def test_ocho_premisas_de_500_caracteres_con_lf_y_crlf(self):
        formula = 'p' * 500
        for separador in ('\n', '\r\n'):
            with self.subTest(separador=repr(separador)):
                response = self.argumento(separador.join([formula] * 8), formula)
                self.assertFalse(response.context['form'].errors)
                result = response.context['argumento']
                self.assertEqual(len(result['premisas']), 8)
                self.assertTrue(result['contradiccion_prueba'])
                self.assertEqual(len(result['filas']), 2)

    def test_margen_de_separadores_no_amplia_limite_por_formula(self):
        for separador in ('\n', '\r\n'):
            with self.subTest(separador=repr(separador)):
                response = self.argumento(separador.join(['p' * 501] + ['p'] * 7), 'p')
                self.assertIn('premisas', response.context['form'].errors)
                self.assertNotIn('argumento', response.context)

    def test_argumento_sin_efectos_academicos(self):
        before = (Intento.objects.count(), Progreso.objects.count())
        self.argumento('p\n~p', 'q')
        self.assertEqual((Intento.objects.count(), Progreso.objects.count()), before)

    def test_ambos_modos_en_cinco_idiomas(self):
        from django.conf import settings
        for language, title in [('es', 'Experimentación libre'), ('en', 'Free exploration'),
                                ('fr', 'Exploration libre'), ('de', 'Freies Experimentieren'),
                                ('zh-hans', '自由探索')]:
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            for response in (self.calcular('p', 'validar'), self.argumento('p', 'p')):
                self.assertContains(response, title)
                self.assertNotContains(response, 'ui.free_exploration')
                self.assertEqual(response['Content-Language'], language)
