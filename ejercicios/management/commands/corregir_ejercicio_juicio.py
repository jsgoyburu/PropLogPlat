"""Management command: corregir_ejercicio_juicio

Re-evalúa todos los intentos de un ejercicio tabla_verdad contra la fórmula
solución actual (ya corregida por el docente) y actualiza es_correcto.

Para los intentos que pasan de incorrecto → correcto, avanza el Progreso.
Los intentos que pasan de correcto → incorrecto se actualizan en la base de
datos pero NO se regresa el Progreso (el docente es responsable del error
original).

Uso:
    python manage.py corregir_ejercicio_juicio --ejercicio-id 42
    python manage.py corregir_ejercicio_juicio --ejercicio-id 42 --dry-run
"""

import json
import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from ejercicios.models import EjercicioPractica, Intento, Progreso
from motor import verificar_argumento
from motor.parser import normalizar_simbolos

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Re-evalúa todos los intentos de un ejercicio tabla_verdad contra su fórmula solución actual.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ejercicio-id',
            type=int,
            required=True,
            help='ID del Ejercicio (tabla_verdad) a re-evaluar.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué cambiaría sin guardar en la base de datos.',
        )

    def handle(self, *args, **options):
        ejercicio_id = options['ejercicio_id']
        dry_run = options['dry_run']

        intentos_qs = (
            Intento.objects
            .filter(
                ejercicio_practica__ejercicio_id=ejercicio_id,
                ejercicio_practica__ejercicio__tipo='tabla_verdad',
                tabla_json__isnull=False,
            )
            .select_related(
                'estudiante',
                'ejercicio_practica__ejercicio',
                'ejercicio_practica__practica',
            )
            .order_by('timestamp')
        )

        total = intentos_qs.count()
        self.stdout.write(f'Total intentos para ejercicio {ejercicio_id}: {total}')

        ahora_correctos = 0
        ahora_incorrectos = 0
        sin_cambio = 0
        pares_afectados = set()

        for intento in intentos_qs:
            ejercicio = intento.ejercicio_practica.ejercicio

            try:
                enunciados_solucion = json.loads(ejercicio.formula_solucion)
            except (json.JSONDecodeError, TypeError):
                self.stdout.write(self.style.WARNING(
                    f'  Intento {intento.id}: formula_solucion inválida — omitido'
                ))
                continue

            try:
                enunciados_estudiante = json.loads(intento.respuesta_raw)
            except (json.JSONDecodeError, TypeError):
                continue

            for e in enunciados_estudiante:
                if 'formula' in e:
                    e['formula'] = normalizar_simbolos(e['formula']).strip()

            try:
                resultado = verificar_argumento(
                    enunciados_estudiante,
                    enunciados_solucion,
                    intento.juicio_estudiante,
                    tabla_estudiante=intento.tabla_json,
                )
            except Exception as exc:
                self.stdout.write(self.style.WARNING(
                    f'  Intento {intento.id}: error al verificar — {exc}'
                ))
                continue

            nuevo = resultado['correcto']
            anterior = intento.es_correcto

            if nuevo == anterior:
                sin_cambio += 1
                continue

            if nuevo and not anterior:
                ahora_correctos += 1
                # La cohorte sale del propio intento (NOT NULL desde 0027):
                # no hace falta adivinarla, y evita pisar el Progreso de la
                # camada equivocada en un recursante.
                pares_afectados.add((
                    intento.estudiante_id,
                    intento.practica_comision_id,
                    intento.cohorte_id,
                    intento.ejercicio_practica.practica_id,
                ))
                self.stdout.write(
                    f'  ✓ Intento {intento.id} | {intento.estudiante} → CORRECTO'
                )
            else:
                ahora_incorrectos += 1
                self.stdout.write(
                    f'  ✗ Intento {intento.id} | {intento.estudiante} → INCORRECTO'
                )

            if not dry_run:
                intento.es_correcto = nuevo
                intento.save(update_fields=['es_correcto'])

        self.stdout.write(
            f'\nIncorrecto→correcto: {ahora_correctos} | '
            f'Correcto→incorrecto: {ahora_incorrectos} | '
            f'Sin cambio: {sin_cambio}'
        )

        progreso_actualizados = 0
        for estudiante_id, pc_id, cohorte_id, practica_id in pares_afectados:
            if self._reconciliar_progreso(estudiante_id, pc_id, cohorte_id, practica_id, dry_run):
                progreso_actualizados += 1

        modo = ' (dry-run, sin cambios guardados)' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'Progreso avanzados: {progreso_actualizados}{modo}'
        ))

    def _reconciliar_progreso(self, estudiante_id, pc_id, cohorte_id, practica_id, dry_run):
        with transaction.atomic():
            progreso = (
                Progreso.objects
                .select_for_update()
                .filter(estudiante_id=estudiante_id, practica_comision_id=pc_id,
                        cohorte_id=cohorte_id)
                .first()
            )
            if progreso is None or progreso.ejercicio_practica_actual is None:
                return False

            ep_original = progreso.ejercicio_practica_actual
            ep_actual = ep_original

            while ep_actual is not None:
                tiene_correcto = Intento.objects.filter(
                    estudiante_id=estudiante_id,
                    ejercicio_practica=ep_actual,
                    practica_comision_id=pc_id,
                    cohorte_id=cohorte_id,
                ).filter(
                    Q(es_correcto=True) | Q(aprobado_docente=True)
                ).exists()

                if not tiene_correcto:
                    break

                ep_actual = (
                    EjercicioPractica.objects
                    .filter(practica_id=practica_id, orden__gt=ep_actual.orden)
                    .order_by('orden')
                    .first()
                )

            if ep_actual == ep_original:
                return False

            self.stdout.write(
                f'  Progreso estudiante {estudiante_id} | PC {pc_id}: '
                f'EP {ep_original.orden} → '
                f'{ep_actual.orden if ep_actual else "completa"}'
            )
            if not dry_run:
                progreso.ejercicio_practica_actual = ep_actual
                progreso.save(update_fields=['ejercicio_practica_actual'])
            return True
