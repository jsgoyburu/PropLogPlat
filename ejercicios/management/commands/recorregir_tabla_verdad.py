"""Management command: recorregir_tabla_verdad

Re-verifica todos los intentos incorrectos de tipo tabla_verdad que tienen
tabla_json guardado. El bug anterior comparaba filas posicionalmente, por lo
que estudiantes que completaron la tabla en un orden de filas distinto al
canónico eran marcados como incorrectos aunque sus valores fueran correctos.

Acciones:
  1. Para cada intento afectado, re-corre verificar_argumento con el código
     corregido.
  2. Si el intento ahora es correcto, actualiza es_correcto=True.
  3. Para cada (estudiante, practica_comision) con al menos un intento recién
     corregido, avanza el Progreso hasta el primer EP sin intento correcto
     (igual que haría _avanzar_progreso en el flujo normal).

Uso:
    python manage.py recorregir_tabla_verdad
    python manage.py recorregir_tabla_verdad --dry-run
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
    help = 'Re-verifica intentos incorrectos de tabla_verdad y corrige es_correcto + Progreso.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué cambiaría sin guardar en la base de datos.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        intentos_qs = (
            Intento.objects
            .filter(
                es_correcto=False,
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
        self.stdout.write(f'Intentos incorrectos de tabla_verdad con tabla: {total}')

        corregidos = 0
        pares_afectados = set()   # (estudiante_id, practica_comision_id, cohorte_id, practica_id)

        for intento in intentos_qs:
            ejercicio = intento.ejercicio_practica.ejercicio

            # Parsear solución
            try:
                enunciados_solucion = json.loads(ejercicio.formula_solucion)
            except (json.JSONDecodeError, TypeError):
                self.stdout.write(
                    self.style.WARNING(
                        f'  Intento {intento.id}: formula_solucion no es JSON válido — omitido'
                    )
                )
                continue

            # Parsear respuesta del estudiante
            try:
                enunciados_estudiante = json.loads(intento.respuesta_raw)
            except (json.JSONDecodeError, TypeError):
                continue

            # Normalizar fórmulas del estudiante
            for e in enunciados_estudiante:
                if 'formula' in e:
                    e['formula'] = normalizar_simbolos(e['formula']).strip()

            tabla_json = intento.tabla_json   # ya es lista de dicts (JSONField)

            try:
                resultado = verificar_argumento(
                    enunciados_estudiante,
                    enunciados_solucion,
                    intento.juicio_estudiante,
                    tabla_estudiante=tabla_json,
                )
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f'  Intento {intento.id}: error al re-verificar — {exc}'
                    )
                )
                continue

            if resultado['correcto']:
                practica_id = intento.ejercicio_practica.practica_id
                self.stdout.write(
                    f'  Intento {intento.id} | {intento.estudiante} | '
                    f'EP {intento.ejercicio_practica_id} → ahora CORRECTO'
                )
                corregidos += 1
                # La cohorte sale del propio intento (NOT NULL desde 0027):
                # no hace falta adivinarla, y evita pisar el Progreso de la
                # camada equivocada en un recursante.
                pares_afectados.add((
                    intento.estudiante_id,
                    intento.practica_comision_id,
                    intento.cohorte_id,
                    practica_id,
                ))

                if not dry_run:
                    intento.es_correcto = True
                    intento.save(update_fields=['es_correcto'])

        self.stdout.write(f'\nIntentos corregidos: {corregidos}')

        # --- Reconciliar Progreso ---
        progreso_actualizados = 0
        for estudiante_id, pc_id, cohorte_id, practica_id in pares_afectados:
            avanzado = self._reconciliar_progreso(estudiante_id, pc_id, cohorte_id, practica_id, dry_run)
            if avanzado:
                progreso_actualizados += 1

        modo = ' (dry-run, sin cambios guardados)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'Progreso actualizados: {progreso_actualizados}{modo}'
            )
        )

    def _reconciliar_progreso(self, estudiante_id, pc_id, cohorte_id, practica_id, dry_run):
        """Avanza el Progreso hasta el primer EP sin intento correcto.

        Un intento cuenta como correcto si es_correcto=True o aprobado_docente=True.
        Filtra por cohorte porque un recursante puede tener dos filas de
        Progreso para el mismo (estudiante, practica_comision), una por camada.
        Devuelve True si el Progreso cambió.
        """
        with transaction.atomic():
            eps = list(
                EjercicioPractica.objects
                .filter(practica_id=practica_id)
                .order_by('orden')
            )
            if not eps:
                return False

            progreso = (
                Progreso.objects
                .select_for_update()
                .filter(estudiante_id=estudiante_id, practica_comision_id=pc_id,
                        cohorte_id=cohorte_id)
                .first()
            )
            if progreso is None:
                return False

            if progreso.ejercicio_practica_actual is None:
                return False   # ya está completada

            ep_original = progreso.ejercicio_practica_actual
            ep_actual = ep_original

            # Avanzar mientras el EP actual tenga un intento aprobado o correcto
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

                siguiente = (
                    EjercicioPractica.objects
                    .filter(practica_id=practica_id, orden__gt=ep_actual.orden)
                    .order_by('orden')
                    .first()
                )
                ep_actual = siguiente

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
