"""Tests del backend de mail por API HTTP.

Viven acá y no en una app porque el backend es infraestructura del proyecto:
lo elige `settings.EMAIL_BACKEND` y lo usa cualquier app que mande mails.
"""

import json
from unittest.mock import patch

from django.core.mail import EmailMultiAlternatives
from django.test import TestCase, override_settings

from logica_ipc.email_backends import BREVO_ENDPOINT, BrevoAPIEmailBackend


class _RespuestaFalsa:
    """Stand-in de lo que devuelve urlopen: context manager con .status."""

    def __init__(self, status=201):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"messageId": "<abc@brevo>"}'


class BrevoAPIEmailBackendTests(TestCase):
    def _mensaje(self, **kwargs):
        datos = {
            'subject': 'Recuperar tu contraseña',
            'body': 'Entrá acá: https://ejemplo.com/reset/',
            'from_email': 'IPC · Lógica <no-reply@practicaslogica.com.ar>',
            'to': ['estudiante@ejemplo.com'],
        }
        datos.update(kwargs)
        return EmailMultiAlternatives(**datos)

    def test_postea_al_endpoint_de_brevo_con_la_api_key(self):
        backend = BrevoAPIEmailBackend(api_key='clave-de-prueba')

        with patch('logica_ipc.email_backends.request.urlopen',
                   return_value=_RespuestaFalsa()) as urlopen:
            enviados = backend.send_messages([self._mensaje()])

        self.assertEqual(enviados, 1)
        pedido = urlopen.call_args.args[0]
        self.assertEqual(pedido.full_url, BREVO_ENDPOINT)
        self.assertEqual(pedido.method, 'POST')
        # urllib capitaliza los nombres de header al guardarlos.
        self.assertEqual(pedido.headers['Api-key'], 'clave-de-prueba')
        self.assertEqual(pedido.headers['Content-type'], 'application/json')

    def test_separa_el_nombre_de_la_direccion_del_remitente(self):
        # Django guarda from_email como "Nombre <mail@dominio>"; la API de Brevo
        # los quiere en campos distintos. Sin separarlos, el sender queda
        # inválido y Brevo rechaza el envío entero.
        backend = BrevoAPIEmailBackend(api_key='clave-de-prueba')

        with patch('logica_ipc.email_backends.request.urlopen',
                   return_value=_RespuestaFalsa()) as urlopen:
            backend.send_messages([self._mensaje()])

        cuerpo = json.loads(urlopen.call_args.args[0].data.decode('utf-8'))
        self.assertEqual(cuerpo['sender'], {
            'name': 'IPC · Lógica',
            'email': 'no-reply@practicaslogica.com.ar',
        })
        self.assertEqual(cuerpo['to'], [{'email': 'estudiante@ejemplo.com'}])
        self.assertEqual(cuerpo['subject'], 'Recuperar tu contraseña')
        self.assertIn('Entrá acá', cuerpo['textContent'])

    def test_una_direccion_pelada_no_inventa_nombre(self):
        backend = BrevoAPIEmailBackend(api_key='clave-de-prueba')

        with patch('logica_ipc.email_backends.request.urlopen',
                   return_value=_RespuestaFalsa()) as urlopen:
            backend.send_messages([self._mensaje(from_email='sola@ejemplo.com')])

        cuerpo = json.loads(urlopen.call_args.args[0].data.decode('utf-8'))
        self.assertEqual(cuerpo['sender'], {'email': 'sola@ejemplo.com'})

    def test_manda_el_html_cuando_hay_alternativa(self):
        backend = BrevoAPIEmailBackend(api_key='clave-de-prueba')
        mensaje = self._mensaje()
        mensaje.attach_alternative('<p>hola</p>', 'text/html')

        with patch('logica_ipc.email_backends.request.urlopen',
                   return_value=_RespuestaFalsa()) as urlopen:
            backend.send_messages([mensaje])

        cuerpo = json.loads(urlopen.call_args.args[0].data.decode('utf-8'))
        self.assertEqual(cuerpo['htmlContent'], '<p>hola</p>')

    def test_sin_html_no_manda_el_campo(self):
        backend = BrevoAPIEmailBackend(api_key='clave-de-prueba')

        with patch('logica_ipc.email_backends.request.urlopen',
                   return_value=_RespuestaFalsa()) as urlopen:
            backend.send_messages([self._mensaje()])

        cuerpo = json.loads(urlopen.call_args.args[0].data.decode('utf-8'))
        self.assertNotIn('htmlContent', cuerpo)

    def test_lista_vacia_no_llama_a_la_api(self):
        backend = BrevoAPIEmailBackend(api_key='clave-de-prueba')

        with patch('logica_ipc.email_backends.request.urlopen') as urlopen:
            self.assertEqual(backend.send_messages([]), 0)

        urlopen.assert_not_called()

    def test_sin_api_key_no_intenta_ni_finge_que_mando(self):
        # Si devolviera 1 sin haber mandado nada, un deploy mal configurado
        # se vería idéntico a uno que funciona.
        backend = BrevoAPIEmailBackend(api_key='', fail_silently=True)

        with patch('logica_ipc.email_backends.request.urlopen') as urlopen:
            self.assertEqual(backend.send_messages([self._mensaje()]), 0)

        urlopen.assert_not_called()

    def test_sin_api_key_y_sin_fail_silently_explota(self):
        backend = BrevoAPIEmailBackend(api_key='', fail_silently=False)

        with self.assertRaises(ValueError):
            backend.send_messages([self._mensaje()])

    def test_un_error_de_red_se_propaga_si_fail_silently_es_false(self):
        backend = BrevoAPIEmailBackend(api_key='clave-de-prueba', fail_silently=False)

        with patch('logica_ipc.email_backends.request.urlopen',
                   side_effect=OSError('sin ruta al host')):
            with self.assertLogs('logica_ipc.email_backends', level='ERROR'):
                with self.assertRaises(OSError):
                    backend.send_messages([self._mensaje()])

    def test_un_error_de_red_se_traga_si_fail_silently_es_true(self):
        backend = BrevoAPIEmailBackend(api_key='clave-de-prueba', fail_silently=True)

        with patch('logica_ipc.email_backends.request.urlopen',
                   side_effect=OSError('sin ruta al host')):
            with self.assertLogs('logica_ipc.email_backends', level='ERROR'):
                self.assertEqual(backend.send_messages([self._mensaje()]), 0)


@override_settings(
    EMAIL_BACKEND='logica_ipc.email_backends.BrevoAPIEmailBackend',
    BREVO_API_KEY='clave-de-prueba',
    DEFAULT_FROM_EMAIL='IPC · Lógica <no-reply@practicaslogica.com.ar>',
)
class RecuperarPasswordPorAPITests(TestCase):
    """El flujo real de recuperación, saliendo por la API en vez de SMTP.

    Es la prueba que importa: que el backend no solo funcione aislado sino que
    `django.contrib.auth` mande por él sin cambiarle nada a la vista.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.cache import cache
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

    def test_el_reset_sale_por_la_api_con_el_link_adentro(self):
        from django.urls import reverse

        with patch('logica_ipc.email_backends.request.urlopen',
                   return_value=_RespuestaFalsa()) as urlopen:
            response = self.client.post(
                reverse('accounts:password_reset'),
                {'email': 'olvido@ejemplo.com'},
            )

        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        urlopen.assert_called_once()
        cuerpo = json.loads(urlopen.call_args.args[0].data.decode('utf-8'))
        self.assertEqual(cuerpo['to'], [{'email': 'olvido@ejemplo.com'}])
        self.assertIn('/accounts/reset/', cuerpo['textContent'])
        self.assertIn('24 horas', cuerpo['textContent'])
