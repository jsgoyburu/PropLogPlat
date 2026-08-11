"""Management command: calcular_categorias_error

Clasifica offline los intentos incorrectos según el tipo de error lógico
y guarda el resultado en ``Intento.error_categoria``.

Diseño:
  - Idempotente: no reprocesa intentos ya categorizados (error_categoria != None).
  - Procesa por lotes para no saturar memoria con datasets grandes.
  - Reporta conteo de procesados y distribucion de categorias al final.
  - No falla silenciosamente: escribe los errores de parseo en stderr.

Uso:
    python manage.py calcular_categorias_error
    python manage.py calcular_categorias_error --comision 3
    python manage.py calcular_categorias_error --limit 500
    python manage.py calcular_categorias_error --reprocesar  # fuerza recalculo
    python manage.py calcular_categorias_error --dry-run     # muestra sin guardar

Categorías de error para formalización:
  polaridad     : tabla de la respuesta = NOT de la solución (todas filas invertidas)
  tautologia    : respuesta siempre verdadera
  contradiccion : respuesta siempre falsa
  parcial       : algunas filas coinciden, otras no
  error_parse   : la respuesta no se puede parsear
  otro          : no clasificado

Categorías de error para tabla de verdad:
  juicio        : tabla correcta pero juicio de validez incorrecto
  columna_premisa   : error en columna de premisa (P1, P2, ...)
  columna_conclusion: error solo en la columna de conclusión (C)
  otro          : error en múltiples columnas o sin tabla_json
"""

import json as _json
from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Q

from ejercicios.models import Intento


class Command(BaseCommand):
    help = 'Clasifica errores lógicos de intentos incorrectos (offline).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=2000,
            help='Máximo de intentos a procesar en esta ejecución (default: 2000).',
        )
        parser.add_argument(
            '--comision',
            type=int,
            help='Procesar solo intentos de esta comisión.',
        )
        parser.add_argument(
            '--reprocesar',
            action='store_true',
            help='Forzar recálculo incluso de intentos ya categorizados.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Calcular y mostrar distribución sin guardar en base de datos.',
        )

    def handle(self, *args, **options):
        qs = Intento.objects.filter(
            Q(aprobado_docente=False)
            | Q(es_correcto=False, aprobado_docente__isnull=True)
        )

        if not options['reprocesar']:
            qs = qs.filter(error_categoria__isnull=True)

        if options.get('comision'):
            qs = qs.filter(
                ejercicio_practica__practica__comision_id=options['comision'],
            )

        qs = qs.select_related(
            'ejercicio_practica__ejercicio',
        ).order_by('id')[:options['limit']]

        procesados = 0
        errores = 0
        conteo = Counter()

        for intento in qs:
            try:
                categoria = _clasificar(intento)
                conteo[categoria] += 1
                if not options['dry_run']:
                    intento.error_categoria = categoria
                    intento.save(update_fields=['error_categoria'])
                procesados += 1
            except Exception as exc:
                errores += 1
                self.stderr.write(
                    f'  Intento {intento.id}: {type(exc).__name__}: {exc}'
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nProcesados: {procesados} intentos '
                f'{"(dry-run, no guardado)" if options["dry_run"] else "(guardado)"}'
            )
        )
        if errores:
            self.stdout.write(self.style.WARNING(f'Errores: {errores}'))
        self.stdout.write('\nDistribución de categorías:')
        for cat, n in sorted(conteo.items(), key=lambda x: -x[1]):
            self.stdout.write(f'  {cat:<25} {n}')


# ─── Clasificadores ───────────────────────────────────────────────────────────

def _clasificar(intento):
    """Devuelve la categoría de error para un intento incorrecto."""
    ejercicio = intento.ejercicio_practica.ejercicio
    if ejercicio.tipo == 'formalizacion':
        return _clasificar_formalizacion(intento.respuesta_raw, ejercicio.formula_solucion)
    elif ejercicio.tipo == 'tabla_verdad':
        return _clasificar_tabla_verdad(intento)
    return 'otro'


def _clasificar_formalizacion(respuesta, formula_solucion):
    """Clasifica un intento de formalización incorrecto por tipo de error semántico."""
    from motor import generar_tabla
    from motor.tabla import columna_resultado

    try:
        tabla_r = generar_tabla(respuesta)
        col_r = columna_resultado(tabla_r)
    except Exception:
        return 'error_parse'

    try:
        tabla_s = generar_tabla(formula_solucion)
        col_s = columna_resultado(tabla_s)
    except Exception:
        # Si la solución no parsea, no podemos clasificar.
        return 'otro'

    # Tautología: respuesta siempre verdadera
    if all(v for v in col_r):
        return 'tautologia'

    # Contradicción: respuesta siempre falsa
    if not any(v for v in col_r):
        return 'contradiccion'

    # Polaridad: respuesta es la negación exacta de la solución
    # (solo si tienen el mismo número de filas — mismas variables)
    if len(col_r) == len(col_s) and all(r != s for r, s in zip(col_r, col_s)):
        return 'polaridad'

    # Error parcial: algunas filas coinciden, otras no
    if len(col_r) == len(col_s):
        coincidentes = sum(1 for r, s in zip(col_r, col_s) if r == s)
        if 0 < coincidentes < len(col_s):
            return 'parcial'

    return 'otro'


def _clasificar_tabla_verdad(intento):
    """Clasifica un intento de tabla de verdad incorrecto por tipo de error."""
    from motor import verificar_argumento

    tabla_json = intento.tabla_json
    if not tabla_json:
        return 'otro'

    ejercicio = intento.ejercicio_practica.ejercicio

    # Obtener enunciados del ejercicio (guardados en formula_solucion como JSON)
    try:
        enunciados_solucion = _json.loads(ejercicio.formula_solucion)
        if not isinstance(enunciados_solucion, list):
            return 'otro'
    except Exception:
        return 'otro'

    # La respuesta_raw también puede contener los enunciados del estudiante
    try:
        enunciados_estudiante = _json.loads(intento.respuesta_raw)
        if not isinstance(enunciados_estudiante, list):
            enunciados_estudiante = enunciados_solucion
    except Exception:
        enunciados_estudiante = enunciados_solucion

    try:
        resultado = verificar_argumento(
            enunciados_estudiante=enunciados_estudiante,
            enunciados_solucion=enunciados_solucion,
            juicio_valido=None,
            tabla_estudiante=tabla_json,
        )
    except Exception:
        return 'otro'

    tabla_ok = resultado.get('tabla_ok', False)
    canonica = resultado.get('tabla_canonica', [])

    # Si la tabla está bien pero el juicio es incorrecto → error de juicio
    if tabla_ok and not resultado.get('correcto', False):
        return 'juicio'

    # Comparar columna a columna vs la canónica
    if canonica and tabla_json:
        columnas_error = _columnas_con_diferencias(tabla_json, canonica)
        if columnas_error:
            # Determinar si el error es solo en conclusión o en premisas
            solo_conclusion = all(c == 'C' for c in columnas_error)
            if solo_conclusion:
                return 'columna_conclusion'
            # Si hay error en columnas de premisa (P1, P2, ...)
            premisas_con_error = [c for c in columnas_error if c.startswith('P')]
            if premisas_con_error:
                return 'columna_premisa'

    return 'otro'


def _columnas_con_diferencias(tabla_estudiante, tabla_canonica):
    """Devuelve las columnas con diferencias entre las dos tablas.

    Solo compara columnas que existen en ambas tablas. Ignora columnas
    de variables atómicas (p, q, r, etc.) que son prefijadas por el frontend.
    """
    if not tabla_estudiante or not tabla_canonica:
        return []
    cols_est = set(tabla_estudiante[0].keys())
    cols_can = set(tabla_canonica[0].keys())
    columnas = cols_est & cols_can

    errores = set()
    for fila_e, fila_c in zip(tabla_estudiante, tabla_canonica):
        for col in columnas:
            if fila_e.get(col) != fila_c.get(col):
                errores.add(col)
    return sorted(errores)
