# motor/tabla.py
"""Generación de tablas de verdad para expresiones proposicionales.

Recibe expresiones :mod:`sympy` ya parseadas (ver :mod:`motor.parser`) y
produce tablas de verdad como listas de diccionarios Python, un diccionario
por fila.

Convenciones de representación
-------------------------------
**Orden de columnas**: las variables se ordenan por primera aparición en la
fórmula (recorrido preorden del árbol AST). Esto preserva la intención del
estudiante: si escribe ``B ⊃ A`` ("Si bebo, me ahogo"), la tabla muestra B
primero y A segundo, que es el orden con que el estudiante la pensó.

**Orden de filas**: de todo-``True`` a todo-``False``, que es el orden
estándar en la enseñanza de lógica proposicional en el ámbito de IPC/CBC-UBA.
Para *n* variables se generan exactamente :math:`2^n` filas.

**Estructura de cada fila**: un ``dict`` con una clave por variable (el nombre
como ``str``) y la clave especial ``'resultado'``::

    {'p': True, 'q': False, 'resultado': True}

Todos los valores son ``bool`` de Python (no :data:`sympy.true`/:data:`sympy.false`).

Caso borde: fórmulas sin variables libres
------------------------------------------
Si la expresión ya fue simplificada por sympy a ``True`` o ``False`` (sin
variables libres, como resultado de ``p & ~p`` simplificado), se devuelve
una sola fila sin claves de variable::

    [{'resultado': True}]

Este caso no debería aparecer en la práctica porque sympy sólo simplifica
tautologías y contradicciones en algunos contextos; en general conserva las
variables.
"""

from itertools import product as cartesian_product
from sympy import Symbol, preorder_traversal


def generar_tabla_desde_expr(expr, variables: list | None = None) -> list[dict]:
    """Genera la tabla de verdad de una expresión sympy.

    Evalúa la expresión para cada combinación posible de valores de verdad
    de sus variables libres, en el orden estándar (de todo-True a todo-False).

    Args:
        expr: expresión :mod:`sympy` válida, típicamente resultado de
            :func:`motor.parser.parsear`. Puede ser cualquier subtipo de
            :class:`sympy.logic.boolalg.Boolean`.

    Returns:
        Lista de ``dict``, una entrada por fila de la tabla. Cada ``dict``
        contiene:

        - Una clave ``str`` por cada variable libre, con valor ``bool``.
        - La clave ``'resultado'`` con el valor ``bool`` de la expresión
          evaluada en esa fila.

        Las claves de variable siguen el orden de primera aparición en la
        fórmula. El orden de las filas va de todo-``True`` a todo-``False``.

        Ejemplo para ``p & q``::

            [
                {'p': True,  'q': True,  'resultado': True},
                {'p': True,  'q': False, 'resultado': False},
                {'p': False, 'q': True,  'resultado': False},
                {'p': False, 'q': False, 'resultado': False},
            ]

    Note:
        La evaluación usa :meth:`sympy.Basic.subs` para sustituir los
        símbolos por valores ``bool`` de Python. sympy convierte ``True``/
        ``False`` a :data:`sympy.true`/:data:`sympy.false` internamente y
        simplifica la expresión. El resultado se convierte a ``bool`` de
        Python con :func:`bool`.

    Examples:
        Tautología::

            >>> from sympy import Symbol
            >>> from sympy.logic.boolalg import Or, Not
            >>> p = Symbol('p')
            >>> generar_tabla_desde_expr(Or(p, Not(p)))
            [{'p': True, 'resultado': True}, {'p': False, 'resultado': True}]

        Contradicción::

            >>> from sympy.logic.boolalg import And
            >>> generar_tabla_desde_expr(And(p, Not(p)))
            [{'p': True, 'resultado': False}, {'p': False, 'resultado': False}]
    """
    # Si no se recibe un orden externo, se infiere por preorden del árbol sympy.
    # Pero sympy puede reordenar los args de Or/And internamente, así que el
    # orden resultante puede no coincidir con lo que escribió la persona usuaria.
    # La forma correcta es pasarle el orden desde extraer_variables_en_orden().
    if variables is None:
        seen: set = set()
        variables = []
        for node in preorder_traversal(expr):
            if isinstance(node, Symbol) and node not in seen:
                seen.add(node)
                variables.append(node)

    filas: list[dict] = []

    # product([True, False], repeat=n) produce las 2^n combinaciones en
    # orden: (T,T,...,T), (T,T,...,F), ..., (F,F,...,F)
    for valores in cartesian_product([True, False], repeat=len(variables)):
        asignacion = dict(zip(variables, valores))

        # subs() acepta Python True/False; los convierte a sympy.true/false
        # internamente y evalúa la expresión. bool() convierte de vuelta.
        resultado_sympy = expr.subs(list(asignacion.items()))
        resultado = bool(resultado_sympy)

        fila: dict = {v.name: val for v, val in asignacion.items()}
        fila['resultado'] = resultado
        filas.append(fila)

    return filas


def columna_resultado(tabla: list[dict]) -> list[bool]:
    """Extrae la columna ``'resultado'`` de una tabla de verdad.

    Utilidad para comparar dos tablas sin necesidad de comparar los
    nombres de las variables. Es la función central usada por
    :func:`motor.verificador.verificar` para determinar equivalencia
    tabular.

    Args:
        tabla: lista de ``dict`` con al menos la clave ``'resultado'``,
            tal como la produce :func:`generar_tabla_desde_expr`.

    Returns:
        Lista de ``bool`` con los valores de la columna ``'resultado'``,
        en el mismo orden que las filas de ``tabla``.

    Examples:
        >>> tabla = [
        ...     {'p': True,  'resultado': False},
        ...     {'p': False, 'resultado': True},
        ... ]
        >>> columna_resultado(tabla)
        [False, True]
    """
    return [fila['resultado'] for fila in tabla]
