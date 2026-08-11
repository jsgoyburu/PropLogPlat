"""Reconciliación histórica por bug de normalización de `v` disyuntiva.

Este comando corrige datos históricos afectados por el caso en el que fórmulas
como ``JvM`` (sin espacios) no se interpretaban como disyunción.

Qué hace:
1. Normaliza ``formula_solucion`` en ejercicios de formalización.
2. Recalcula intentos de esos ejercicios usando la lógica actual.
3. Actualiza ``es_correcto`` y normaliza ``respuesta_raw`` cuando corresponda.

Uso típico:
    python manage.py reconciliar_disyuncion_v --dry-run
    python manage.py reconciliar_disyuncion_v
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from ejercicios.models import Ejercicio, Intento
from motor.parser import normalizar_simbolos
from motor.verificador import verificar


class Command(BaseCommand):
    help = (
        'Recalcula ejercicios/intentos afectados por el bug histórico de '
        'normalización de "v" como disyunción.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra el impacto sin guardar cambios.',
        )
        parser.add_argument(
            '--limit-intentos',
            type=int,
            default=None,
            help='Procesa como máximo N intentos (útil para corridas graduales).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit_intentos = options['limit_intentos']

        ejercicios = list(
            Ejercicio.objects.filter(tipo='formalizacion')
            .only('id', 'formula_solucion')
            .order_by('id')
        )

        ejercicios_afectados = []
        formulas_actualizadas = 0
        for ejercicio in ejercicios:
            formula_nueva = normalizar_simbolos(ejercicio.formula_solucion).strip()
            if formula_nueva != (ejercicio.formula_solucion or '').strip():
                ejercicios_afectados.append((ejercicio.id, formula_nueva))
                formulas_actualizadas += 1
                if not dry_run:
                    Ejercicio.objects.filter(pk=ejercicio.id).update(
                        formula_solucion=formula_nueva,
                    )

        ids_afectados = [eid for eid, _ in ejercicios_afectados]
        if not ids_afectados:
            self.stdout.write(self.style.SUCCESS('No hay ejercicios afectados.'))
            return

        intentos_qs = (
            Intento.objects
            .filter(ejercicio_practica__ejercicio_id__in=ids_afectados)
            .select_related('ejercicio_practica__ejercicio')
            .order_by('id')
        )
        if limit_intentos:
            intentos_qs = intentos_qs[:limit_intentos]

        intentos_procesados = 0
        intentos_cambiados = 0
        cambiaron_a_correcto = 0
        cambiaron_a_incorrecto = 0
        errores_recalculo = 0

        for intento in intentos_qs:
            ejercicio = intento.ejercicio_practica.ejercicio
            respuesta_nueva = normalizar_simbolos(intento.respuesta_raw).strip()
            resultado = verificar(respuesta_nueva, ejercicio.formula_solucion)
            nuevo_correcto = bool(resultado.get('correcto', False))

            update_fields = []
            if intento.respuesta_raw != respuesta_nueva:
                intento.respuesta_raw = respuesta_nueva
                update_fields.append('respuesta_raw')
            if intento.es_correcto != nuevo_correcto:
                if nuevo_correcto:
                    cambiaron_a_correcto += 1
                else:
                    cambiaron_a_incorrecto += 1
                intento.es_correcto = nuevo_correcto
                intento.error_categoria = None
                update_fields.extend(['es_correcto', 'error_categoria'])
                # Nunca auto-aprobar al docente. Si el intento estaba rechazado
                # y ahora pasa a correcto por la reconciliación, vuelve a
                # pendiente de revisión docente.
                if nuevo_correcto and intento.aprobado_docente is False:
                    intento.aprobado_docente = None
                    update_fields.append('aprobado_docente')

            intentos_procesados += 1
            if update_fields:
                intentos_cambiados += 1
                if not dry_run:
                    try:
                        with transaction.atomic():
                            intento.save(update_fields=update_fields)
                    except Exception:
                        errores_recalculo += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Ejercicios con fórmula actualizada: {formulas_actualizadas}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Intentos procesados: {intentos_procesados}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Intentos con cambios: {intentos_cambiados} '
                f'(→ correcto: {cambiaron_a_correcto}, '
                f'→ incorrecto: {cambiaron_a_incorrecto})'
            )
        )
        if errores_recalculo:
            self.stdout.write(
                self.style.WARNING(
                    f'Errores al guardar intentos: {errores_recalculo}'
                )
            )
        if dry_run:
            self.stdout.write(
                self.style.WARNING('Dry-run activo: no se guardó ningún cambio.')
            )
