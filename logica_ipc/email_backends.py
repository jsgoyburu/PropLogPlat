"""Backend de mail que sale por la API HTTP de Brevo en vez de SMTP.

Por qué existe
--------------
Railway **bloquea los puertos SMTP salientes** (25, 465, 587 y 2525) en los
planes Free, Trial y Hobby; solo los abre en Pro. Con el backend SMTP de
Django, el deploy no puede conectarse a ningún proveedor y la recuperación de
contraseña queda muda de la peor manera: la persona ve la pantalla de "revisá
tu correo" y no le llega nada nunca. El 443 no se bloquea en ningún plan, así
que la API HTTP funciona siempre.

Por qué a mano y no con una biblioteca
--------------------------------------
Usa `urllib` de la biblioteca estándar, igual que `ejercicios/gemini_hints.py`
hace con Gemini y Groq. `requirements.txt` está pinneado a propósito desde que
el rebuild del 2026-08-07 tiró abajo los dos servicios: sumar `django-anymail`
por un POST de veinte líneas no lo justifica.

Cómo se activa
--------------
Poniendo `BREVO_API_KEY` en el entorno. Ver el bloque Email de `settings.py`:
con esa variable gana este backend, sin ella cae al SMTP y, sin `EMAIL_HOST`,
a la consola.

Contrato de la API: POST https://api.brevo.com/v3/smtp/email, con la clave en
el header `api-key`, y `{sender, to, subject, textContent}` en el cuerpo.
Devuelve 201 con un `messageId`.
"""

import json
import logging
from email.utils import parseaddr
from urllib import error, request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = 'https://api.brevo.com/v3/smtp/email'


class BrevoAPIEmailBackend(BaseEmailBackend):
    """Manda cada mensaje como un POST al endpoint transaccional de Brevo."""

    def __init__(self, fail_silently=False, api_key=None, timeout=None, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = (
            api_key
            if api_key is not None
            else getattr(settings, 'BREVO_API_KEY', '')
        )
        self.timeout = timeout or getattr(settings, 'EMAIL_TIMEOUT', None) or 10

    def send_messages(self, email_messages):
        """Devuelve cuántos mensajes se enviaron efectivamente."""
        if not email_messages:
            return 0

        if not self.api_key:
            # Devolver len(email_messages) acá haría que un deploy sin
            # configurar se viera idéntico a uno que funciona.
            if not self.fail_silently:
                raise ValueError(
                    'BREVO_API_KEY no está configurada: el backend de Brevo no '
                    'puede enviar nada.'
                )
            logger.error('BREVO_API_KEY no está configurada; no se envió nada.')
            return 0

        return sum(1 for m in email_messages if self._enviar_uno(m))

    def _enviar_uno(self, message):
        pedido = request.Request(
            BREVO_ENDPOINT,
            data=json.dumps(self._payload(message)).encode('utf-8'),
            headers={
                'api-key': self.api_key,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method='POST',
        )
        try:
            with request.urlopen(pedido, timeout=self.timeout) as respuesta:
                return 200 <= respuesta.status < 300
        except error.HTTPError as e:
            # El cuerpo del error trae el motivo real (remitente no verificado,
            # clave inválida, dominio sin autenticar). Sin loguearlo, depurar
            # una configuración nueva es a ciegas.
            detalle = e.read().decode('utf-8', errors='replace')[:500]
            logger.error('Brevo rechazó el envío (HTTP %s): %s', e.code, detalle)
            if not self.fail_silently:
                raise
            return False
        except OSError:
            # Timeout, DNS, conexión rechazada. HTTPError hereda de OSError, así
            # que este except va después.
            logger.exception('No se pudo contactar la API de Brevo.')
            if not self.fail_silently:
                raise
            return False

    def _payload(self, message):
        """Traduce un EmailMessage de Django al JSON que espera Brevo."""
        nombre, direccion = parseaddr(
            message.from_email or settings.DEFAULT_FROM_EMAIL
        )
        remitente = {'email': direccion}
        if nombre:
            remitente['name'] = nombre

        payload = {
            'sender': remitente,
            'to': [{'email': d} for d in message.to],
            'subject': message.subject,
            'textContent': message.body,
        }

        if message.cc:
            payload['cc'] = [{'email': d} for d in message.cc]
        if message.bcc:
            payload['bcc'] = [{'email': d} for d in message.bcc]
        if message.reply_to:
            r_nombre, r_direccion = parseaddr(message.reply_to[0])
            payload['replyTo'] = {'email': r_direccion}
            if r_nombre:
                payload['replyTo']['name'] = r_nombre

        html = self._html_alternativo(message)
        if html is not None:
            payload['htmlContent'] = html

        return payload

    @staticmethod
    def _html_alternativo(message):
        for alternativa in getattr(message, 'alternatives', None) or []:
            contenido, tipo = alternativa
            if tipo == 'text/html':
                return contenido
        return None
