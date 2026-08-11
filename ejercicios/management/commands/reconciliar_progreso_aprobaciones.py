"""Management command: reconciliar_progreso_aprobaciones

Corrige retroactivamente el Progreso de estudiantes que tenían intentos
incorrectos aprobados por el docente (aprobado_docente=True, es_correcto=False)
antes de que el sistema avanzara el progreso automáticamente en la aprobación.

Diseño:
  - Idempotente: avanzar el progreso solo si el ejercicio actual ya tiene
    un intento aprobado (correcto o por docente).
  - Encadenamiento: si varios ejercicios consecutivos fueron aprobados, avanza
    hasta el primero sin aprobar.
  - Soporta --dry-run para previsualizar cambios sin guardar.
  - Reporta cuántos Progreso se actualizaron.

Uso:
    python manage.py reconciliar_progreso_aprobaciones
    python manage.py reconciliar_progreso_aprobaciones --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from ejercicios.models import EjercicioPractica, Intento, Practica, Progreso


class Command(BaseCommand):
    help = 'Avanza retroactivamente el Progreso de estudiantes con intentos incorrectos aprobados.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué cambiaría sin guardar en la base de datos.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        actualizados = 0
        sin_cambios = 0

        # Estudiantes con al menos un intento incorrecto aprobado. La cohorte
        # sale del propio Intento (NOT NULL desde 0027): cada intento ya sabe
        # a qué camada pertenece, así que no hay que adivinarla.
        pares = (
            Intento.objects
            .filter(es_correcto=False, aprobado_docente=True)
            .values('estudiante_id', 'practica_comision_id', 'cohorte_id',
                    'ejercicio_practica__practica_id')
            .distinct()
        )

        for par in pares:
            estudiante_id = par['estudiante_id']
            pc_id = par['practica_comision_id']
            cohorte_id = par['cohorte_id']
            practica_id = par['ejercicio_practica__practica_id']

            avanzado = self._reconciliar(estudiante_id, pc_id, cohorte_id, practica_id, dry_run)
            if avanzado:
                actualizados += 1
            else:
                sin_cambios += 1

        modo = '(dry-run, sin cambios guardados)' if dry_run else '(guardado)'
        self.stdout.write(
            self.style.SUCCESS(
                f'\nProgreso actualizados: {actualizados} {modo}'
            )
        )
        self.stdout.write(f'Ya estaban correctos: {sin_cambios}')

    def _reconciliar(self, estudiante_id, pc_id, cohorte_id, practica_id, dry_run):
        """Avanza el Progreso de un (estudiante, practica_comision, cohorte) hasta
        el primer ejercicio sin intento aprobado. Devuelve True si hubo cambios."""
        with transaction.atomic():
            progreso = (
                Progreso.objects
                .select_for_update()
                .filter(estudiante_id=estudiante_id, practica_comision_id=pc_id,
                        cohorte_id=cohorte_id)
                .first()
            )

            if progreso is None:
                # No existe Progreso: verificar si hay intentos aprobados para
                # crear el Progreso en el ejercicio correcto.
                primer_ep = (
                    EjercicioPractica.objects
                    .filter(practica_id=practica_id)
                    .order_by('orden')
                    .first()
                )
                if primer_ep is None:
                    return False
                progreso, _ = Progreso.objects.get_or_create(
                    estudiante_id=estudiante_id,
                    practica_comision_id=pc_id,
                    cohorte_id=cohorte_id,
                    defaults={'ejercicio_practica_actual': primer_ep},
                )
                progreso = (
                    Progreso.objects
                    .select_for_update()
                    .get(estudiante_id=estudiante_id, practica_comision_id=pc_id,
                         cohorte_id=cohorte_id)
                )

            if progreso.ejercicio_practica_actual is None:
                return False  # Práctica ya completada

            ep_inicial = progreso.ejercicio_practica_actual
            ep_actual = ep_inicial

            while ep_actual is not None:
                tiene_aprobado = Intento.objects.filter(
                    estudiante_id=estudiante_id,
                    ejercicio_practica=ep_actual,
                    practica_comision_id=pc_id,
                    cohorte_id=cohorte_id,
                    aprobado_docente=True,
                ).exists()

                if not tiene_aprobado:
                    break

                siguiente = (
                    EjercicioPractica.objects
                    .filter(practica_id=practica_id, orden__gt=ep_actual.orden)
                    .order_by('orden')
                    .first()
                )
                ep_actual = siguiente

            hubo_cambio = ep_actual != ep_inicial
            if hubo_cambio:
                self.stdout.write(
                    f'  Estudiante {estudiante_id} | PC {pc_id}: '
                    f'ep {ep_inicial.orden} → '
                    f'{ep_actual.orden if ep_actual else "completa"}'
                )
                if not dry_run:
                    progreso.ejercicio_practica_actual = ep_actual
                    progreso.save(update_fields=['ejercicio_practica_actual'])

            return hubo_cambio
