"""Management command: poblar_error_categoria

Re-clasifica todos los intentos incorrectos de tipo formalización que todavía
no tienen categoría de error asignada (``error_categoria=None``).

Usa el clasificador semántico en :mod:`motor.clasificador`.

Diseño:
  - Idempotente: por defecto no reprocesa intentos ya categorizados.
  - Procesa en lotes para no saturar memoria.
  - Con ``--dry-run`` muestra la distribución proyectada sin guardar.
  - Con ``--reprocesar`` fuerza recalculo aunque ya tengan categoría.
  - Con ``--comision`` limita a una comisión.

Uso:
    python manage.py poblar_error_categoria --dry-run
    python manage.py poblar_error_categoria
    python manage.py poblar_error_categoria --comision 3
    python manage.py poblar_error_categoria --limit 1000 --reprocesar
"""

from collections import Counter

from django.core.management.base import BaseCommand

from ejercicios.models import Intento
from motor.clasificador import clasificar_error


class Command(BaseCommand):
    help = (
        'Clasifica semánticamente los intentos incorrectos de formalización '
        'y popula Intento.error_categoria.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=5000,
            help='Máximo de intentos a procesar (default: 5000).',
        )
        parser.add_argument(
            '--comision',
            type=int,
            help='Procesar solo intentos de esta comisión.',
        )
        parser.add_argument(
            '--reprocesar',
            action='store_true',
            help='Recalcular incluso intentos ya categorizados.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Calcular y mostrar distribución sin guardar.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        qs = (
            Intento.objects
            .filter(
                es_correcto=False,
                ejercicio_practica__ejercicio__tipo='formalizacion',
            )
            .exclude(error_categoria='error_parse')  # ya clasificados como parse error
            .select_related('ejercicio_practica__ejercicio')
            .order_by('id')
        )

        if not options['reprocesar']:
            qs = qs.filter(error_categoria__isnull=True)

        if options.get('comision'):
            qs = qs.filter(
                practica_comision__comision_id=options['comision'],
            )

        qs = qs[:options['limit']]

        procesados = 0
        errores = 0
        conteo = Counter()

        for intento in qs:
            ejercicio = intento.ejercicio_practica.ejercicio
            try:
                categoria = clasificar_error(
                    intento.respuesta_raw,
                    ejercicio.formula_solucion,
                )
                conteo[categoria] += 1
                if not dry_run:
                    intento.error_categoria = categoria
                    intento.save(update_fields=['error_categoria'])
                procesados += 1
            except Exception as exc:
                errores += 1
                self.stderr.write(
                    f'  Intento {intento.id}: {type(exc).__name__}: {exc}'
                )

        modo = ' (dry-run, no guardado)' if dry_run else ' (guardado)'
        self.stdout.write(
            self.style.SUCCESS(f'\nProcesados: {procesados} intentos{modo}')
        )
        if errores:
            self.stdout.write(self.style.WARNING(f'Errores inesperados: {errores}'))

        self.stdout.write('\nDistribución de categorías:')
        for cat, n in sorted(conteo.items(), key=lambda x: -x[1]):
            self.stdout.write(f'  {cat:<25} {n:>6}')
