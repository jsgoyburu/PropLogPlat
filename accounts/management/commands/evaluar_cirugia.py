"""Evalúa con Groq las respuestas al acertijo de cirugía del onboarding.

Uso:
    python manage.py evaluar_cirugia           # evalúa solo las pendientes (null)
    python manage.py evaluar_cirugia --todos   # re-evalúa todas (sobreescribe)
"""

from django.core.management.base import BaseCommand

from accounts.models import EncuestaEstudiante
from ejercicios.gemini_hints import evaluar_cirugia_groq


class Command(BaseCommand):
    help = 'Evalúa con Groq las respuestas al acertijo de cirugía del onboarding.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--todos',
            action='store_true',
            help='Re-evalúa todas las encuestas, incluso las ya evaluadas.',
        )

    def handle(self, *args, **options):
        qs = EncuestaEstudiante.objects.all()
        if not options['todos']:
            qs = qs.filter(acertijo_cirugia_correcto__isnull=True)

        total = qs.count()
        self.stdout.write(f'Evaluando {total} encuesta(s)...')

        evaluadas = errores = sin_respuesta = 0
        for enc in qs.only('id', 'acertijo_cirugia', 'acertijo_cirugia_correcto'):
            cirugia = (enc.acertijo_cirugia or '').strip()
            if not cirugia:
                enc.acertijo_cirugia_correcto = False
                enc.save(update_fields=['acertijo_cirugia_correcto'])
                sin_respuesta += 1
                continue

            resultado = evaluar_cirugia_groq(cirugia)
            if resultado is not None:
                enc.acertijo_cirugia_correcto = resultado
                enc.save(update_fields=['acertijo_cirugia_correcto'])
                evaluadas += 1
            else:
                errores += 1
                self.stderr.write(f'  Sin evaluar: encuesta id={enc.id}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Listo — evaluadas: {evaluadas}, sin respuesta: {sin_respuesta}, '
                f'error Groq: {errores}'
            )
        )
