# motor/clasificador.py
"""Clasificador automático de errores lógicos en ejercicios de formalización.

Analiza la fórmula de un estudiante comparándola semánticamente con la
solución y devuelve una categoría de error que describe el tipo de distancia
lógica entre ambas.

La función central es :func:`clasificar_error`. Solo debe llamarse cuando
ya se sabe que el intento es incorrecto (``es_correcto=False``) y el tipo
de ejercicio es ``formalizacion``.

Categorías de error
--------------------
``tautologia``
    La fórmula del estudiante es siempre verdadera.
``contradiccion``
    La fórmula del estudiante es siempre falsa.
``polaridad``
    La fórmula del estudiante es semánticamente la negación exacta de la
    solución (todas las filas de resultado invertidas).
``mas_fuerte``
    La solución implica semánticamente a la fórmula del estudiante, pero
    no a la inversa. El estudiante añadió un caso (una disyunción).
``mas_debil``
    La fórmula del estudiante implica semánticamente a la solución, pero
    no a la inversa. El estudiante perdió una condición.
``equivalente_alt``
    Las tablas son idénticas (distancia = 0) pero el motor rechazó la
    respuesta por alguna otra causa (variables incorrectas, etc.).
    Señal de "revisar manualmente".
``error_parcial_1``
    Distancia semántica exactamente 1 fila.
``error_parcial_2``
    Distancia semántica exactamente 2 filas.
``error_sistemico``
    Distancia semántica mayor a la mitad de las filas totales. El error
    no es puntual sino estructural.
``variables_extra``
    El estudiante usó más variables que la solución.
``variables_menos``
    El estudiante usó menos variables que la solución.
``sin_clasificar``
    No encaja en ninguna categoría anterior (distancias intermedias, etc.).

Dependencias
------------
Este módulo es Python puro y no importa nada de Django. Solo importa desde
:mod:`motor.parser` y :mod:`motor.tabla`.

No importar directamente desde el stack web: siempre usar a través de
:func:`motor.verificador.distancia_semantica` o de este módulo.
"""

from itertools import product as _cartesian, permutations as _perms

from sympy import Symbol

from .parser import parsear
from .tabla import generar_tabla_desde_expr, columna_resultado


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _vars_sym(expr) -> list:
    """Retorna las variables libres de una expresión, ordenadas por nombre."""
    return sorted(expr.free_symbols, key=lambda s: s.name)


def _col_canonica(expr, variables: list) -> list[bool]:
    """Evalúa expr para todas las combinaciones de variables en orden canónico.

    El orden canónico es: variables ordenadas alfabéticamente, filas de
    todo-True a todo-False (lexicográfico sobre los valores).
    """
    return [
        bool(expr.subs(list(zip(variables, vals))))
        for vals in _cartesian([True, False], repeat=len(variables))
    ]


def _entails(col_a: list[bool], col_b: list[bool]) -> bool:
    """True si A ⊨ B: en todas las filas donde A=True, B=True."""
    return all(b for a, b in zip(col_a, col_b) if a)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def clasificar_error(formula_estudiante: str, formula_solucion: str) -> str:
    """Clasifica el tipo de error semántico en un intento de formalización.

    Compara la fórmula del estudiante con la solución y devuelve una de las
    categorías de error definidas en este módulo. Solo debe llamarse cuando
    ``es_correcto=False``.

    Args:
        formula_estudiante: fórmula enviada por el estudiante (ASCII normalizado).
        formula_solucion: fórmula solución del ejercicio (ASCII normalizado).

    Returns:
        Cadena con la categoría de error. Siempre devuelve algo; nunca lanza
        excepciones (los errores de parseo devuelven ``'sin_clasificar'``).
    """
    # Parsear ambas fórmulas; cualquier error → sin_clasificar
    try:
        expr_est = parsear(formula_estudiante)
    except (ValueError, Exception):
        return 'sin_clasificar'

    try:
        expr_sol = parsear(formula_solucion)
    except (ValueError, Exception):
        return 'sin_clasificar'

    vars_est = frozenset(v.name for v in expr_est.free_symbols)
    vars_sol = frozenset(v.name for v in expr_sol.free_symbols)

    # Columna canónica de la fórmula del estudiante (sobre sus propias variables)
    vars_est_sym = _vars_sym(expr_est)
    col_est = _col_canonica(expr_est, vars_est_sym)

    # 1. Tautología: respuesta siempre verdadera
    if all(col_est):
        return 'tautologia'

    # 2. Contradicción: respuesta siempre falsa
    if not any(col_est):
        return 'contradiccion'

    # 3. Variables distintas en cantidad
    if len(vars_est) > len(vars_sol):
        return 'variables_extra'
    if len(vars_est) < len(vars_sol):
        return 'variables_menos'

    # A partir de aquí: mismo número de variables (pueden ser iguales o distintas).
    vars_sol_sym = _vars_sym(expr_sol)
    n = len(vars_sol_sym)

    # Columna canónica de la solución
    col_sol = _col_canonica(expr_sol, vars_sol_sym)

    # Si mismas variables: comparación directa
    if vars_est == vars_sol:
        return _clasificar_mismas_variables(col_est, col_sol)

    # Variables distintas (mismo n): encontrar la permutación de mínima distancia
    # y trabajar sobre ella.
    min_dist = None
    mejor_col_est = None
    for perm in _perms(vars_est_sym):
        col_perm = _col_canonica(expr_est, list(perm))
        dist = sum(a != b for a, b in zip(col_perm, col_sol))
        if min_dist is None or dist < min_dist:
            min_dist = dist
            mejor_col_est = col_perm

    return _clasificar_por_distancia(mejor_col_est, col_sol, min_dist, n)


def _clasificar_mismas_variables(
    col_est: list[bool], col_sol: list[bool]
) -> str:
    """Clasifica cuando ambas fórmulas tienen el mismo conjunto de variables."""
    n = len(col_sol)
    dist = sum(a != b for a, b in zip(col_est, col_sol))

    # Polaridad: todas las filas invertidas
    if dist == n:
        return 'polaridad'

    return _clasificar_por_distancia(col_est, col_sol, dist, n)


def _clasificar_por_distancia(
    col_est: list[bool],
    col_sol: list[bool],
    dist: int,
    n: int,
) -> str:
    """Clasifica basándose en la distancia semántica y la entailment."""
    # Equivalente alternativo: misma tabla (distancia 0) pero motor rechazó
    if dist == 0:
        return 'equivalente_alt'

    # dist=1: señal puntual tan precisa que no debe ceder a implicación semántica
    if dist == 1:
        return 'error_parcial_1'

    # dist > n//2: error estructural claro, ídem
    if dist > n // 2:
        return 'error_sistemico'

    # Para el resto: la relación de implicación semántica es más informativa
    sol_entails_est = _entails(col_sol, col_est)
    est_entails_sol = _entails(col_est, col_sol)

    if sol_entails_est and not est_entails_sol:
        return 'mas_fuerte'
    if est_entails_sol and not sol_entails_est:
        return 'mas_debil'

    if dist == 2:
        return 'error_parcial_2'

    return 'sin_clasificar'
