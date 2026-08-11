"""Management command: revisar_diccionarios_groq

Aplica la revisión automática de diccionarios con Groq a los intentos con
corrección automática correcta que todavía no tienen veredicto docente.

Solo procesa intentos con diccionario no vacío y revision_diccionario vacío
(es decir, los que nunca fueron enviados a Groq). Con --reprocesar también
recalcula los que ya tienen veredicto.

Requiere GROQ_API_KEY en el entorno. Falla con error explícito si no está
configurada.

Uso:
    python manage.py revisar_diccionarios_groq --dry-run
    python manage.py revisar_diccionarios_groq
    python manage.py revisar_diccionarios_groq --comision 3
    python manage.py revisar_diccionarios_groq --limit 500 --reprocesar
"""

import os
import time
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from ejercicios.models import Intento
from ejercicios.gemini_hints import revisar_diccionario_groq


class Command(BaseCommand):
    help = (
        'Revisa con Groq el diccionario de los intentos correctos pendientes '
        'y popula Intento.revision_diccionario.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=2000,
            help='Máximo de intentos a procesar (default: 2000).',
        )
        parser.add_argument(
            '--comision',
            type=int,
            help='Procesar solo intentos de esta comisión.',
        )
        parser.add_argument(
            '--reprocesar',
            action='store_true',
            help='Recalcular incluso intentos que ya tienen veredicto.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar cuántos intentos se procesarían sin guardar ni llamar a Groq.',
        )
        parser.add_argument(
            '--pausa-ms',
            type=int,
            default=200,
            help='Pausa entre llamadas a Groq en milisegundos (default: 200).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if not dry_run and not os.environ.get('GROQ_API_KEY', '').strip():
            raise CommandError(
                'GROQ_API_KEY no está configurada. '
                'Exportá la variable de entorno antes de ejecutar este comando.'
            )

        qs = (
            Intento.objects
            .filter(
                es_correcto=True,
                aprobado_docente__isnull=True,
            )
            .exclude(diccionario={})
            .select_related('ejercicio_practica__ejercicio')
            .order_by('id')
        )

        if not options['reprocesar']:
            # Por defecto: sin veredicto o marcados 'revisar' (pueden estar mal clasificados).
            # Con --reprocesar se vuelven a evaluar también los 'pasa'.
            qs = qs.filter(revision_diccionario__in=['', 'revisar'])

        if options.get('comision'):
            qs = qs.filter(practica_comision__comision_id=options['comision'])

        qs = qs[:options['limit']]

        total = qs.count()
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'Dry-run: {total} intento(s) serían procesados (sin llamar a Groq).'
                )
            )
            return

        procesados = 0
        errores = 0
        conteo = Counter()
        pausa = options['pausa_ms'] / 1000.0

        self.stdout.write(f'Procesando {total} intento(s)...')

        for intento in qs:
            ejercicio = intento.ejercicio_practica.ejercicio
            try:
                veredicto = revisar_diccionario_groq(ejercicio.enunciado, intento.diccionario)
                if veredicto:
                    intento.revision_diccionario = veredicto
                    intento.save(update_fields=['revision_diccionario'])
                    conteo[veredicto] += 1
                else:
                    conteo['sin_respuesta'] += 1
                procesados += 1
                if pausa > 0:
                    time.sleep(pausa)
            except Exception as exc:
                errores += 1
                self.stderr.write(f'  Intento {intento.id}: {type(exc).__name__}: {exc}')

        self.stdout.write(self.style.SUCCESS(f'\nProcesados: {procesados} intento(s).'))
        if errores:
            self.stdout.write(self.style.WARNING(f'Errores inesperados: {errores}'))

        self.stdout.write('\nDistribución de veredictos:')
        for veredicto, n in sorted(conteo.items(), key=lambda x: -x[1]):
            self.stdout.write(f'  {veredicto:<20} {n:>6}')
