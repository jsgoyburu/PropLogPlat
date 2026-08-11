"""Reevalua intentos de ejercicios de tabla de verdad.

El comando recalcula la verificacion formal automatica (`es_correcto`) con el
motor actual y reconcilia el progreso para los estudiantes que tengan intentos
formalmente correctos. No modifica `aprobado_docente`: la evaluacion docente
permanece separada de la verificacion formal de la maquina.

Uso:
    python manage.py reevaluar_tablas_verdad
    python manage.py reevaluar_tablas_verdad --dry-run
    python manage.py reevaluar_tablas_verdad --ejercicio-id 12
"""

import json

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from ejercicios.models import EjercicioPractica, Intento, Progreso
from motor import verificar_argumento
from motor.parser import normalizar_simbolos


class Command(BaseCommand):
    help = (
        "Reevalua todos los intentos de tabla_verdad con el motor actual, "
        "actualiza es_correcto y reconcilia Progreso."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ejercicio-id",
            type=int,
            default=None,
            help="Limita la reevaluacion a un Ejercicio especifico.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra que cambiaria sin guardar modificaciones.",
        )

    def handle(self, *args, **options):
        ejercicio_id = options["ejercicio_id"]
        dry_run = options["dry_run"]

        intentos_qs = (
            Intento.objects
            .filter(
                ejercicio_practica__ejercicio__tipo="tabla_verdad",
                tabla_json__isnull=False,
            )
            .select_related(
                "estudiante",
                "ejercicio_practica__ejercicio",
                "ejercicio_practica__practica",
                "practica_comision",
            )
            .order_by("timestamp", "id")
        )
        if ejercicio_id is not None:
            intentos_qs = intentos_qs.filter(ejercicio_practica__ejercicio_id=ejercicio_id)

        total = intentos_qs.count()
        modo = " (dry-run)" if dry_run else ""
        self.stdout.write(f"Intentos tabla_verdad a reevaluar: {total}{modo}")

        cambios_a_correcto = 0
        cambios_a_incorrecto = 0
        sin_cambio = 0
        omitidos = 0
        pares_a_reconciliar = set()
        comisiones_a_invalidar = set()  # pares (comision_id, cohorte_id)

        for intento in intentos_qs.iterator(chunk_size=200):
            resultado = self._verificar_intento(intento)
            if resultado is None:
                omitidos += 1
                continue

            nuevo = bool(resultado["correcto"])
            anterior = intento.es_correcto

            if nuevo:
                # La cohorte sale del propio intento (NOT NULL desde 0027):
                # no hace falta adivinarla.
                pares_a_reconciliar.add((
                    intento.estudiante_id,
                    intento.practica_comision_id,
                    intento.cohorte_id,
                    intento.ejercicio_practica.practica_id,
                ))
                comisiones_a_invalidar.add((
                    intento.practica_comision.comision_id, intento.cohorte_id,
                ))

            update_fields = []
            if nuevo != anterior:
                intento.es_correcto = nuevo
                update_fields.append("es_correcto")
                if nuevo:
                    cambios_a_correcto += 1
                    self.stdout.write(
                        f"  Intento {intento.id} | {intento.estudiante} -> verificado automaticamente"
                    )
                else:
                    cambios_a_incorrecto += 1
                    self.stdout.write(
                        f"  Intento {intento.id} | {intento.estudiante} -> no verificado"
                    )
            else:
                sin_cambio += 1

            if nuevo and intento.error_categoria is not None:
                intento.error_categoria = None
                update_fields.append("error_categoria")

            if update_fields and not dry_run:
                intento.save(update_fields=update_fields)

        progresos_actualizados = 0
        for estudiante_id, pc_id, cohorte_id, practica_id in pares_a_reconciliar:
            if self._reconciliar_progreso(estudiante_id, pc_id, cohorte_id, practica_id, dry_run):
                progresos_actualizados += 1

        if not dry_run:
            for comision_id, cohorte_id in comisiones_a_invalidar:
                cache.delete(f"analiticas_{comision_id}_{cohorte_id}")

        self.stdout.write(
            "\n"
            f"Incorrecto->verificado: {cambios_a_correcto} | "
            f"Verificado->no verificado: {cambios_a_incorrecto} | "
            f"Sin cambio: {sin_cambio} | "
            f"Omitidos: {omitidos}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Progresos reconciliados: {progresos_actualizados}{modo}"
            )
        )

    def _verificar_intento(self, intento):
        ejercicio = intento.ejercicio_practica.ejercicio
        try:
            enunciados_solucion = json.loads(ejercicio.formula_solucion)
            enunciados_estudiante = json.loads(intento.respuesta_raw)
        except (json.JSONDecodeError, TypeError):
            self.stdout.write(
                self.style.WARNING(
                    f"  Intento {intento.id}: JSON invalido en solucion o respuesta; omitido"
                )
            )
            return None

        for enunciado in enunciados_estudiante:
            if "formula" in enunciado:
                enunciado["formula"] = normalizar_simbolos(enunciado["formula"]).strip()

        try:
            return verificar_argumento(
                enunciados_estudiante,
                enunciados_solucion,
                intento.juicio_estudiante,
                tabla_estudiante=intento.tabla_json,
            )
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(
                    f"  Intento {intento.id}: error al reevaluar ({exc}); omitido"
                )
            )
            return None

    def _reconciliar_progreso(self, estudiante_id, pc_id, cohorte_id, practica_id, dry_run):
        with transaction.atomic():
            ejercicios = list(
                EjercicioPractica.objects
                .filter(practica_id=practica_id)
                .order_by("orden")
            )
            if not ejercicios:
                return False

            ejercicio_actual = None
            for ep in ejercicios:
                resuelto = (
                    Intento.objects
                    .filter(estudiante_id=estudiante_id, ejercicio_practica=ep,
                            practica_comision_id=pc_id, cohorte_id=cohorte_id)
                    .filter(Q(es_correcto=True) | Q(aprobado_docente=True))
                    .exists()
                )
                if not resuelto:
                    ejercicio_actual = ep
                    break

            progreso = (
                Progreso.objects
                .select_for_update()
                .filter(estudiante_id=estudiante_id, practica_comision_id=pc_id,
                        cohorte_id=cohorte_id)
                .first()
            )
            actual_id = ejercicio_actual.id if ejercicio_actual else None

            if progreso is None:
                if not dry_run:
                    Progreso.objects.create(
                        estudiante_id=estudiante_id,
                        practica_comision_id=pc_id,
                        cohorte_id=cohorte_id,
                        ejercicio_practica_actual=ejercicio_actual,
                    )
                return True

            if progreso.ejercicio_practica_actual_id == actual_id:
                return False

            # Nunca retroceder progreso historico. Si ya esta completa
            # (actual=None) o si apunta a un ejercicio posterior al primer
            # pendiente recalculado, se conserva el avance alcanzado.
            if progreso.ejercicio_practica_actual is None:
                return False
            if ejercicio_actual is not None and progreso.ejercicio_practica_actual.orden > ejercicio_actual.orden:
                return False

            if not dry_run:
                progreso.ejercicio_practica_actual = ejercicio_actual
                progreso.save(update_fields=["ejercicio_practica_actual"])
            return True
