"""Comando de management: crear_admin_inicial.

Crea el primer superusuario a partir de variables de entorno.
Se ejecuta automáticamente en el Procfile (release step) solo si
no existe ningún superusuario en la base de datos.

Variables de entorno requeridas:
    ADMIN_USERNAME  — nombre de usuario del admin inicial
    ADMIN_EMAIL     — email del admin inicial
    ADMIN_PASSWORD  — contraseña del admin inicial

Si alguna de las tres falta, el comando termina sin error (para no
romper el deploy en entornos que ya tienen superusuarios creados
manualmente).
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Crea el superusuario inicial desde variables de entorno '
        '(ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD). '
        'No hace nada si ya existe algún superusuario.'
    )

    def handle(self, *args, **options):
        Usuario = get_user_model()

        if Usuario.objects.filter(is_superuser=True).exists():
            self.stdout.write('Admin inicial: ya existe un superusuario, se omite la creación.')
            return

        username = os.environ.get('ADMIN_USERNAME', '').strip()
        email    = os.environ.get('ADMIN_EMAIL', '').strip()
        password = os.environ.get('ADMIN_PASSWORD', '').strip()

        if not (username and email and password):
            self.stdout.write(
                self.style.WARNING(
                    'Admin inicial: ADMIN_USERNAME, ADMIN_EMAIL o ADMIN_PASSWORD no están definidas. '
                    'Se omite la creación del superusuario.'
                )
            )
            return

        Usuario.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            es_docente=True,
            debe_cambiar_password=False,
            consentimiento_pedagogico=False,
            consentimiento_investigacion=False,
            consentimiento_contacto_seguimiento=False,
            encuesta_completada=True,
        )
        from accounts.models import ConfigSitio
        config = ConfigSitio.get()
        config.instalacion_completada = True
        config.save(update_fields=['instalacion_completada'])
        self.stdout.write(
            self.style.SUCCESS(f'Admin inicial creado: {username} ({email})')
        )
