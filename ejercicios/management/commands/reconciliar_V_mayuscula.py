"""Reconciliación histórica de intentos de formalización marcados como incorrectos.

Corrige dos bugs del verificador que afectaban ejercicios de formalización:

Bug 1 — 'V' mayúscula no normalizada:
    normalizar_simbolos() no convertía 'V' mayúscula al símbolo de disyunción
    '∨'. El parser la trataba como variable extra, generando tablas más largas.

Bug 2 — Permutación de nombres de variables:
    El verificador no detectaba equivalencia cuando el estudiante usaba letras
    distintas a las de la solución para las mismas proposiciones (p. ej. la
    solución usa A=Juan-fanático, B=María-fanática, y el estudiante usa
    O=Juan-fanático, A=María-fanática). El nuevo verificador prueba todas las
    biyecciones posibles entre variables.

Qué hace este comando:
1. Busca todos los intentos de formalización con es_correcto=False.
2. Re-normaliza respuesta_raw (corrige V mayúscula si corresponde).
3. Re-verifica con el verificador corregido (permutaciones incluidas).
4. Para los intentos que ahora son correctos:
   - Actualiza es_correcto=True y normaliza respuesta_raw.
   - Limpia error_categoria.
   - Establece aprobado_docente=True (aprobación automática histórica),
     excepto si ya tenía aprobado_docente=True.
5. Avanza el progreso de cada estudiante bloqueado/a en un ejercicio afectado.
6. Invalida los cachés de analíticas de las comisiones afectadas.

Idempotente: puede ejecutarse múltiples veces sin doble efecto.

Uso:
    python manage.py reconciliar_V_mayuscula --dry-run
    python manage.py reconciliar_V_mayuscula
"""

import collections

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction

from ejercicios.models import EjercicioPractica, Intento, Progreso
from motor.parser import normalizar_simbolos
from motor.verificador import verificar


class Command(BaseCommand):
    help = (
        'Corrige intentos históricos marcados como incorrectos por el bug '
        'de normalización de "V" mayúscula como disyunción.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra el impacto sin guardar ningún cambio.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # ── 1. Candidatos: todos los intentos incorrectos de formalización ──
        # Se re-verifican con el verificador corregido (normalización de V
        # mayúscula + detección de equivalencia bajo permutación de variables).
        candidatos = list(
            Intento.objects
            .filter(
                es_correcto=False,
                ejercicio_practica__ejercicio__tipo='formalizacion',
            )
            .select_related(
                'ejercicio_practica__ejercicio',
                'ejercicio_practica__practica',
                'practica_comision__comision',
                'estudiante',
            )
            .order_by('id')
        )

        self.stdout.write(f'Intentos incorrectos de formalización a revisar: {len(candidatos)}')

        corregidos = 0           # intentos que cambian de False → True
        sin_cambio = 0           # siguen siendo incorrectos con el verificador nuevo
        errores = 0              # fórmulas solución inválidas (bug del docente)

        # Conjunto de (estudiante_id, practica_comision_id, practica_id)
        # corregidos, para luego avanzar el progreso en orden.
        progreso_pendiente: dict[tuple, list] = collections.defaultdict(list)
        comisiones_afectadas: set[tuple[int, int]] = set()  # (comision_id, cohorte_id)

        for intento in candidatos:
            # Re-normalizar (corrige V mayúscula entre otros casos).
            respuesta_nueva = normalizar_simbolos(intento.respuesta_raw).strip()
            formula_solucion = intento.ejercicio_practica.ejercicio.formula_solucion
            try:
                resultado = verificar(respuesta_nueva, formula_solucion)
            except RuntimeError:
                # La fórmula solución del ejercicio es inválida (bug del docente).
                errores += 1
                continue

            if not resultado['correcto']:
                # Incluso con V normalizado, la respuesta sigue siendo incorrecta.
                sin_cambio += 1
                continue

            # ── El intento es ahora correcto ─────────────────────────────
            corregidos += 1

            if not dry_run:
                update_fields = ['es_correcto', 'respuesta_raw', 'error_categoria']
                intento.es_correcto = True
                intento.respuesta_raw = respuesta_nueva
                intento.error_categoria = None

                # Auto-aprobar si aún no fue revisado. Si el docente ya
                # había aprobado manualmente (True) no tocamos nada.
                # Si estaba rechazado (False), corregimos a aprobado.
                if intento.aprobado_docente is not True:
                    intento.aprobado_docente = True
                    update_fields.append('aprobado_docente')

                try:
                    with transaction.atomic():
                        intento.save(update_fields=update_fields)
                except Exception as exc:
                    self.stderr.write(
                        f'Error al guardar intento {intento.id}: {exc}'
                    )
                    errores += 1
                    continue

            # Registrar para avance de progreso (en orden de ejercicio). La
            # cohorte sale del propio Intento (NOT NULL desde 0027): no hace
            # falta adivinarla, y es necesaria para no pisar el Progreso de
            # otra camada del mismo (estudiante, practica_comision).
            ep = intento.ejercicio_practica
            key = (intento.estudiante_id, intento.practica_comision_id,
                   intento.cohorte_id, ep.practica_id)
            progreso_pendiente[key].append(ep)

            comision_id = intento.practica_comision.comision_id
            if comision_id:
                comisiones_afectadas.add((comision_id, intento.cohorte_id))

        # ── 2. Avanzar progreso en orden ascendente de ejercicio ────────────
        avances = 0
        if not dry_run:
            for (student_id, pc_id, cohorte_id, practica_id), eps in progreso_pendiente.items():
                # Ordenar por orden del ejercicio para avanzar step by step.
                eps_ordenados = sorted(set(ep.pk for ep in eps))
                eps_por_pk = {ep.pk: ep for ep in eps}

                for ep_pk in eps_ordenados:
                    ep = eps_por_pk[ep_pk]
                    avanzado = self._avanzar_progreso(student_id, pc_id, cohorte_id, practica_id, ep)
                    if avanzado:
                        avances += 1

        # ── 3. Invalidar cachés de analíticas ───────────────────────────────
        if not dry_run:
            for comision_id, cohorte_id in comisiones_afectadas:
                cache.delete(f'analiticas_{comision_id}_{cohorte_id}')

        # ── Resumen ──────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f'Intentos corregidos (False → True, aprobados): {corregidos}'
        ))
        self.stdout.write(
            f'Intentos sin cambio (siguen siendo incorrectos): {sin_cambio}'
        )
        if errores:
            self.stdout.write(self.style.WARNING(
                f'Errores (solución inválida o fallo al guardar): {errores}'
            ))
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'Avances de progreso realizados: {avances}'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'Cachés de analíticas invalidados: {len(comisiones_afectadas)}'
            ))
        if dry_run:
            self.stdout.write(self.style.WARNING(
                'Dry-run activo: no se guardó ningún cambio.'
            ))

    @staticmethod
    def _avanzar_progreso(student_id: int, pc_id: int, cohorte_id: int, practica_id: int, ep: EjercicioPractica) -> bool:
        """Avanza el progreso del estudiante si está bloqueado en ep.

        Replica la lógica de IntentoCreateView._avanzar_progreso pero
        acepta IDs en lugar de instancias para evitar N+1 en el command.
        Solo actúa si ejercicio_practica_actual == ep; en otro caso es no-op.
        Filtra por cohorte porque un recursante puede tener dos filas de
        Progreso para el mismo (estudiante, practica_comision), una por camada.

        Returns:
            True si se avanzó el progreso (el estudiante estaba bloqueado aquí).
        """
        try:
            with transaction.atomic():
                progreso = (
                    Progreso.objects
                    .select_for_update()
                    .filter(estudiante_id=student_id, practica_comision_id=pc_id,
                            cohorte_id=cohorte_id)
                    .first()
                )
                if progreso is None or progreso.ejercicio_practica_actual_id != ep.pk:
                    return False

                siguiente = (
                    EjercicioPractica.objects
                    .filter(practica_id=practica_id, orden__gt=ep.orden)
                    .order_by('orden')
                    .first()
                )
                progreso.ejercicio_practica_actual = siguiente
                progreso.save(update_fields=['ejercicio_practica_actual'])
                return True
        except Exception:
            return False
