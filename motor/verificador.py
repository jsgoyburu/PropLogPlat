# motor/verificador.py
"""Interfaz pública del motor lógico.

Este módulo es el único punto de entrada que el resto del proyecto Django
necesita conocer. Expone tres funciones según la especificación del AGENTS.md:

- :func:`verificar` — comparación tabular de dos fórmulas.
- :func:`generar_tabla` — tabla de verdad de una fórmula.
- :func:`parsear` — parseo de una fórmula (re-exportado desde :mod:`motor.parser`).

Separación de responsabilidades
---------------------------------
Este módulo **no importa nada de Django**. Es Python puro y puede ser
ejecutado y testeado con :mod:`pytest` sin levantar el proyecto Django.
Esa es una decisión de diseño explícita (AGENTS.md §3): el motor es una
biblioteca lógica reemplazable independientemente del stack web.

Flujo de una corrección
------------------------
El flujo típico desde una view Django es::

    from motor import verificar

    resultado = verificar(respuesta_raw, ejercicio.formula_solucion)
    if resultado["correcto"]:
        # actualizar progreso del estudiante
        ...
    else:
        # devolver feedback con tablas lado a lado
        tabla_est = resultado["tabla_estudiante"]
        tabla_sol = resultado["tabla_solucion"]
        error = resultado["error_parse"]   # None si no hubo error de sintaxis

Equivalencia tabular
---------------------
La corrección se hace comparando las **columnas de resultado** de las tablas
de verdad, no la forma sintáctica. Esto acepta formalizaciones equivalentes
semánticamente (``p -> q`` equivale a ``~p | q``), pero tiene limitaciones
conocidas y aceptadas (ver :func:`verificar`).
"""

from itertools import product as cartesian_product, permutations as all_permutations

from sympy import Symbol, preorder_traversal
from sympy.logic.boolalg import And, Or, Not, Implies, Equivalent

from .parser import parsear, validar_parentesis_en_operaciones_mixtas, extraer_variables_en_orden, _tokenize
from .tabla import generar_tabla_desde_expr, columna_resultado


# ---------------------------------------------------------------------------
# Helper: evaluación puntual de una fórmula
# ---------------------------------------------------------------------------

def _evaluar_con_valores(expr, valores: dict) -> bool:
    """Evalúa ``expr`` sustituyendo cada variable por su valor booleano.

    Args:
        expr: expresión sympy.
        valores: ``{"A": True, "B": False}``.

    Returns:
        Resultado booleano de la evaluación.
    """
    subs = [(Symbol(k), bool(v)) for k, v in valores.items()]
    return bool(expr.subs(subs))


# ---------------------------------------------------------------------------
# Árbol binario propio para preservar estructura de subfórmulas
# ---------------------------------------------------------------------------

class _Nodo:
    """Árbol binario que preserva la estructura sintáctica escrita.

    Sympy aplana And/Or por ser asociativos: And(And(A,B),C) → And(A,B,C).
    Eso hace que _subformulas_postorden pierda el nodo intermedio A·B.
    _Nodo mantiene la estructura binaria original y delega la evaluación
    a la expresión sympy almacenada en _sympy.
    """
    __slots__ = ('op', '_hijos', '_sympy')

    def __init__(self, op: str, hijos: tuple, sympy_expr):
        self.op = op          # 'ATOM' | 'NOT' | 'AND' | 'OR' | 'IMPLIES' | 'IFF'
        self._hijos = hijos   # tuple of _Nodo
        self._sympy = sympy_expr

    def subs(self, subs_list):
        return self._sympy.subs(subs_list)

    @property
    def free_symbols(self):
        return self._sympy.free_symbols


def _nodo_a_copi(n: '_Nodo') -> str:
    """Convierte un _Nodo a notación Copi preservando la estructura binaria."""
    def _par(child: '_Nodo') -> str:
        s = _nodo_a_copi(child)
        return f'({s})' if child.op != 'ATOM' else s

    if n.op == 'ATOM':
        return n._sympy.name
    if n.op == 'NOT':
        return f'~{_par(n._hijos[0])}'
    if n.op == 'AND':
        return f'{_par(n._hijos[0])} · {_par(n._hijos[1])}'
    if n.op == 'OR':
        return f'{_par(n._hijos[0])} ∨ {_par(n._hijos[1])}'
    if n.op == 'IMPLIES':
        return f'{_par(n._hijos[0])} ⊃ {_par(n._hijos[1])}'
    if n.op == 'IFF':
        return f'{_par(n._hijos[0])} ≡ {_par(n._hijos[1])}'
    return str(n._sympy)


def _nodo_subformulas_postorden(n: '_Nodo') -> list:
    """Subfórmulas no atómicas en orden postorden (bottom-up)."""
    if n.op == 'ATOM':
        return []
    result = []
    for hijo in n._hijos:
        result.extend(_nodo_subformulas_postorden(hijo))
    result.append(n)
    return result


def _parsear_nodo(formula: str) -> '_Nodo':
    """Parsea una fórmula en un árbol _Nodo preservando la estructura binaria.

    Reconstruye la misma gramática que motor.parser._Parser pero produce
    _Nodo en lugar de expresiones sympy, de modo que la estructura binaria
    escrita (p.ej. el paréntesis en '(A·B)·C') queda codificada en el árbol
    y no se pierde por el aplanamiento interno de sympy.
    """
    tokens = _tokenize(formula.strip())
    pos = [0]

    def peek():
        return tokens[pos[0]][0]

    def consume():
        tok = tokens[pos[0]]
        pos[0] += 1
        return tok

    def formula_():
        return iff_()

    def iff_():
        left = implies_()
        while peek() == 'IFF':
            consume()
            right = implies_()
            left = _Nodo('IFF', (left, right), Equivalent(left._sympy, right._sympy))
        return left

    def implies_():
        left = or_()
        if peek() == 'IMPLIES':
            consume()
            right = implies_()
            return _Nodo('IMPLIES', (left, right), Implies(left._sympy, right._sympy))
        return left

    def or_():
        left = and_()
        while peek() == 'OR':
            consume()
            right = and_()
            left = _Nodo('OR', (left, right), Or(left._sympy, right._sympy))
        return left

    def and_():
        left = not_()
        while peek() == 'AND':
            consume()
            right = not_()
            left = _Nodo('AND', (left, right), And(left._sympy, right._sympy))
        return left

    def not_():
        if peek() == 'NEG':
            consume()
            child = not_()
            return _Nodo('NOT', (child,), Not(child._sympy))
        return atom_()

    def atom_():
        if peek() == 'LPAREN':
            consume()           # (
            n = formula_()
            consume()           # )
            return n
        tok = consume()
        sym = Symbol(tok[1])
        return _Nodo('ATOM', (), sym)

    return formula_()


# ---------------------------------------------------------------------------
# Helpers privados para tabla con subcolumnas
# ---------------------------------------------------------------------------

def _generar_tabla_con_subcolumnas(
    exprs: list,
    enunciados: list[dict],
    variables: list,
) -> list[dict]:
    """Genera la tabla completa del argumento con subcolumnas intermedias.

    Usa _parsear_nodo para obtener el árbol binario de cada enunciado,
    preservando la estructura parentética escrita. Así '(A·B)·C' genera
    una subcolumna para 'A·B' y otra para '(A·B)·C', en lugar de una
    sola 'A·B·C' como produciría sympy (que aplana And/Or internamente).

    Args:
        exprs: expresiones sympy (para compatibilidad; ya no se usan para
            extraer subformulas, solo para respaldar evaluación si _parsear_nodo
            falla).
        enunciados: lista de dicts {"formula": str, "tipo": str}.
        variables: variables del argumento en orden (de aparición).
    """
    # Construir árbol binario desde la fórmula original de cada enunciado.
    nodos: list = []
    for expr, e in zip(exprs, enunciados):
        formula = e.get('formula', '').strip()
        try:
            nodos.append(_parsear_nodo(formula))
        except Exception:
            # Fallback: nodo atómico sintético si el parseo falla
            nodos.append(_Nodo('ATOM', (), expr))

    etiquetas_ordenadas: list[tuple] = []  # (_Nodo, label) en orden de primera aparición
    labels_vistos: set[str] = set()
    labels_finales: list[str] = []

    for nodo, e in zip(nodos, enunciados):
        subs_list = _nodo_subformulas_postorden(nodo)
        intermedias = subs_list[:-1] if nodo.op != 'ATOM' else []

        for sub in intermedias:
            lbl = _nodo_a_copi(sub)
            if lbl not in labels_vistos:
                labels_vistos.add(lbl)
                etiquetas_ordenadas.append((sub, lbl))

        label_final = _nodo_a_copi(nodo)
        if label_final not in labels_vistos:
            labels_vistos.add(label_final)
            etiquetas_ordenadas.append((nodo, label_final))
        labels_finales.append(label_final)

    filas = []
    for valores in cartesian_product([True, False], repeat=len(variables)):
        asig = list(zip(variables, valores))
        fila = {v.name: val for v, val in zip(variables, valores)}
        for sub_expr, label in etiquetas_ordenadas:
            fila[label] = bool(sub_expr.subs(asig))
        filas.append(fila)
    return filas, etiquetas_ordenadas, labels_finales


# ---------------------------------------------------------------------------
# Interfaz pública
# ---------------------------------------------------------------------------

def generar_tabla(formula: str) -> list[dict]:
    """Genera la tabla de verdad de una fórmula proposicional.

    Parsea la fórmula y delega la generación a
    :func:`motor.tabla.generar_tabla_desde_expr`.

    Args:
        formula: cadena en ASCII normalizado, p.ej. ``'p -> (q & ~r)'``.
            Ver :func:`motor.parser.parsear` para la sintaxis completa.

    Returns:
        Lista de ``dict``, una entrada por fila. Cada ``dict`` tiene una
        clave ``str`` por variable (con valor ``bool``) y la clave
        ``'resultado'`` (``bool``). Las variables están ordenadas
        alfabéticamente; las filas van de todo-``True`` a todo-``False``.

        Ejemplo para ``'p -> q'``::

            [
                {'p': True,  'q': True,  'resultado': True},
                {'p': True,  'q': False, 'resultado': False},
                {'p': False, 'q': True,  'resultado': True},
                {'p': False, 'q': False, 'resultado': True},
            ]

    Raises:
        ValueError: si la fórmula no es válida sintácticamente. El mensaje
            es legible en español y puede mostrarse al usuario.

    Examples:
        Tautología::

            >>> from motor import generar_tabla
            >>> tabla = generar_tabla('p | ~p')
            >>> all(f['resultado'] for f in tabla)
            True

        Contradicción::

            >>> tabla = generar_tabla('p & ~p')
            >>> any(f['resultado'] for f in tabla)
            False
    """
    expr = parsear(formula)          # puede lanzar ValueError
    variables = [Symbol(n) for n in extraer_variables_en_orden(formula)]
    return generar_tabla_desde_expr(expr, variables)


def verificar(respuesta: str, solucion: str) -> dict:
    """Compara la respuesta de un estudiante con la solución por equivalencia tabular.

    La comparación es **semántica**, no sintáctica: se comparan las columnas
    de resultado de las tablas de verdad. Esto acepta formalizaciones
    equivalentes (p.ej. ``~p | q`` como respuesta a ``p -> q``) y tiene las
    siguientes limitaciones conocidas y aceptadas (AGENTS.md §5):

    - **Variables distintas**: ``p -> q`` y ``a -> b`` son tabularmente
      equivalentes (misma función booleana, mismo número de variables). El
      motor las acepta como correctas. El motor no puede detectar que el
      estudiante usó nombres de variable distintos a los de la solución.
    - **Tautología vs. tautología**: si la solución es una tautología, se
      acepta cualquier tautología del estudiante, independientemente del
      número de variables. El docente debe ser consciente de esto al
      cargar ejercicios con soluciones tautológicas.
    - **Contradicción vs. contradicción**: ídem para contradicciones.

    Args:
        respuesta: fórmula del estudiante en ASCII normalizado.
        solucion: fórmula solución cargada por el docente, en ASCII
            normalizado.

    Returns:
        ``dict`` con las siguientes claves:

        ``correcto`` (:class:`bool`)
            ``True`` si la respuesta es tabularmente equivalente a la
            solución.

        ``error_parse`` (:class:`str` or ``None``)
            Mensaje de error en español si la fórmula del estudiante no
            pudo parsearse; ``None`` si el parseo fue exitoso. Cuando esta
            clave no es ``None``, ``tabla_estudiante`` es ``None`` y
            ``correcto`` es ``False``.

        ``tabla_estudiante`` (:class:`list` of :class:`dict` or ``None``)
            Tabla de verdad de la respuesta del estudiante (formato
            idéntico al de :func:`generar_tabla`). ``None`` si hubo
            error de parseo.

        ``tabla_solucion`` (:class:`list` of :class:`dict` or ``None``)
            Tabla de verdad de la solución. ``None`` si hubo error de
            parseo en la respuesta (en ese caso no se llega a parsear
            la solución).

    Raises:
        RuntimeError: si la fórmula **solución** no pudo parsearse. Esto
            indica un bug en la carga del ejercicio (responsabilidad del
            docente o del admin), no un error del estudiante. La view
            Django debe capturar este error y loguearlo como error del
            sistema.

    Note:
        La función **nunca lanza excepciones** por errores en la respuesta
        del estudiante. Los errores de parseo del estudiante se devuelven
        en el campo ``error_parse`` del dict de retorno.

    Examples:
        Respuesta correcta (equivalencia semántica)::

            >>> from motor import verificar
            >>> r = verificar('~p | q', 'p -> q')
            >>> r['correcto']
            True
            >>> r['error_parse'] is None
            True

        Respuesta incorrecta::

            >>> r = verificar('p & q', 'p -> q')
            >>> r['correcto']
            False

        Error de parseo en la respuesta::

            >>> r = verificar('p ∧ q', 'p & q')
            >>> r['correcto']
            False
            >>> r['error_parse']
            "Carácter no reconocido: '∧' — Usar '·' para la conjunción (notación Copi)."
            >>> r['tabla_estudiante'] is None
            True

        Bug en la solución del docente (RuntimeError)::

            >>> verificar('p & q', 'p &&& q')
            RuntimeError: La fórmula solución del ejercicio no es válida: ...
    """
    # --- Parsear respuesta del estudiante ---
    try:
        validar_parentesis_en_operaciones_mixtas(respuesta)
        expr_respuesta = parsear(respuesta)
    except ValueError as e:
        # Presentar un mensaje amigable al estudiante; el detalle técnico
        # se incluye entre paréntesis para facilitar la depuración pero sin
        # ser el mensaje principal.
        detalle = str(e)
        mensaje = f'La fórmula ingresada no es una fórmula bien formada (fbf). ({detalle})'
        return {
            "correcto": False,
            "error_parse": mensaje,
            "error_parse_detalle": detalle,
            "tabla_estudiante": None,
            "tabla_solucion": None,
        }

    # --- Parsear solución (errores aquí son bugs del sistema, no del alumno) ---
    try:
        expr_solucion = parsear(solucion)
    except ValueError as e:
        raise RuntimeError(
            f"La fórmula solución del ejercicio no es válida: {e}. "
            "Esto es un error en la carga del ejercicio y debe corregirse."
        ) from e

    # --- Generar tablas preservando el orden de variables escrito por cada autor ---
    vars_resp = [Symbol(n) for n in extraer_variables_en_orden(respuesta)]
    vars_sol  = [Symbol(n) for n in extraer_variables_en_orden(solucion)]
    tabla_estudiante = generar_tabla_desde_expr(expr_respuesta, vars_resp)
    tabla_solucion   = generar_tabla_desde_expr(expr_solucion,  vars_sol)

    # --- Comparar columnas de resultado ---
    res_estudiante = columna_resultado(tabla_estudiante)
    res_solucion   = columna_resultado(tabla_solucion)

    # Casos especiales (AGENTS.md §5):
    # - Tautología vs. tautología: si ambas columnas son todo-True, se aceptan
    #   como equivalentes sin importar el número de variables. El docente debe
    #   ser consciente de que cargar una tautología acepta cualquier tautología.
    # - Contradicción vs. contradicción: ídem para todo-False.
    if all(res_solucion) and all(res_estudiante):
        correcto = True
    elif not any(res_solucion) and not any(res_estudiante):
        correcto = True
    else:
        # Caso general: comparación columna a columna.
        # Distinto número de variables → tablas de distinto largo → False.
        #
        # NOTA sobre orden de variables: generar_tabla_desde_expr usa primera
        # aparición en la fórmula. Sympy puede reordenar args de Or/And
        # internamente (forma canónica), así que dos fórmulas equivalentes
        # (ej. p⊃q y ~p∨q) pueden generar tablas con distinto orden de filas.
        # Cuando ambas tienen el mismo conjunto de variables, re-ordenamos
        # las filas por orden canónico (alfabético) antes de comparar.
        # Esto no afecta las tablas devueltas al usuario, solo la comparación.
        vars_respuesta = frozenset(v.name for v in expr_respuesta.free_symbols)
        vars_solucion  = frozenset(v.name for v in expr_solucion.free_symbols)
        if vars_respuesta == vars_solucion and vars_respuesta:
            var_names = sorted(vars_respuesta)
            sort_key = lambda row: tuple(not row[v] for v in var_names)
            correcto = (
                [r['resultado'] for r in sorted(tabla_estudiante, key=sort_key)]
                == [r['resultado'] for r in sorted(tabla_solucion, key=sort_key)]
            )
        elif len(vars_respuesta) == len(vars_solucion) and vars_respuesta:
            # Mismo número de variables pero nombres distintos.
            # El estudiante puede haber usado letras distintas a las de la
            # solución para las mismas proposiciones. Probamos todas las
            # biyecciones posibles renombrando las variables directamente en
            # las expresiones Sympy (subs), igual que _equivalentes() en
            # verificar_argumento(). Para n variables: n! permutaciones.
            vars_resp_sym = sorted(expr_respuesta.free_symbols, key=lambda s: s.name)
            vars_sol_sym  = sorted(expr_solucion.free_symbols,  key=lambda s: s.name)
            n = len(vars_sol_sym)
            col_sol = [
                bool(expr_solucion.subs(list(zip(vars_sol_sym, vals))))
                for vals in cartesian_product([True, False], repeat=n)
            ]
            correcto = any(
                [bool(expr_respuesta.subs(list(zip(perm, vals))))
                 for vals in cartesian_product([True, False], repeat=n)] == col_sol
                for perm in all_permutations(vars_resp_sym)
            )
        else:
            correcto = res_estudiante == res_solucion

    return {
        "correcto": correcto,
        "error_parse": None,
        "tabla_estudiante": tabla_estudiante,
        "tabla_solucion": tabla_solucion,
    }


def verificar_argumento(
    enunciados_estudiante: list[dict],
    enunciados_solucion: list[dict],
    juicio_valido,
    tabla_estudiante: list[dict] | None = None,
) -> dict:
    """Verifica la respuesta de un estudiante a un ejercicio de argumento lógico.

    Un argumento es un conjunto de enunciados donde algunos son premisas y
    uno es la conclusión. El argumento es **válido** si no existe ninguna
    interpretación donde todas las premisas son verdaderas y la conclusión
    es falsa.

    La corrección requiere:
    1. Que las fórmulas del estudiante coincidan (por equivalencia tabular)
       con las de la solución, respetando el tipo (premisa/conclusión).
       El orden de los enunciados no importa.
    2. Que el juicio de validez del estudiante coincida con el real.

    Args:
        enunciados_estudiante: lista de dicts ``{"formula": str, "tipo": str}``
            donde ``tipo`` es ``"premisa"`` o ``"conclusion"``.
        enunciados_solucion: misma estructura, obtenida del JSON guardado
            por el docente en ``Ejercicio.formula_solucion``.
        juicio_valido: ``True`` si el estudiante marcó que el argumento es
            válido, ``False`` si marcó que no lo es, ``None`` si no marcó nada.

    Returns:
        ``dict`` con las siguientes claves:

        ``correcto`` (:class:`bool`)
            ``True`` si todas las fórmulas coinciden con sus tipos Y el
            juicio de validez es correcto.

        ``errores_parse`` (:class:`list`)
            Lista con un elemento por fórmula del estudiante. Cada elemento
            es ``None`` si la fórmula parseó correctamente, o un ``str`` con
            el mensaje de error si falló.

        ``tabla_argumento`` (:class:`list` of :class:`dict` or ``None``)
            Tabla combinada del argumento de la solución. Cada fila tiene:
            - las variables (ordenadas alfabéticamente): ``bool``
            - ``"P1"``, ``"P2"``, ...: resultado de cada premisa (``bool``)
            - ``"C"``: resultado de la conclusión (``bool``)
            - ``"valido_fila"``: ``False`` cuando todas las premisas son
              ``True`` y la conclusión es ``False``
            ``None`` si alguna fórmula del estudiante tiene error de parseo.

        ``es_valido`` (:class:`bool` or ``None``)
            ``True`` si el argumento de la solución es lógicamente válido.
            ``None`` si la tabla no pudo construirse.

        ``juicio_estudiante_valido`` (:class:`bool` or ``None``)
            El juicio enviado por el estudiante.

        ``formulas_ok`` (:class:`bool`)
            ``True`` si todas las fórmulas de la solución fueron matcheadas
            por fórmulas del estudiante del mismo tipo, sin sobrar ni faltar.

    Raises:
        RuntimeError: si alguna fórmula de la **solución** no pudo parsearse.
            Esto indica un bug en la carga del ejercicio.
    """
    # --- Parsear fórmulas del estudiante ---
    exprs_estudiante = []
    errores_parse = []
    hay_error = False
    for e in enunciados_estudiante:
        formula = e.get('formula', '').strip()
        try:
            validar_parentesis_en_operaciones_mixtas(formula)
            expr = parsear(formula)
            exprs_estudiante.append(expr)
            errores_parse.append(None)
        except ValueError as exc:
            detalle = str(exc)
            mensaje = f'La fórmula ingresada no es una fórmula bien formada (fbf). ({detalle})'
            exprs_estudiante.append(None)
            errores_parse.append(mensaje)
            hay_error = True

    # --- Parsear fórmulas de la solución (errores son bugs del sistema) ---
    exprs_solucion = []
    for e in enunciados_solucion:
        formula = e.get('formula', '').strip()
        try:
            expr = parsear(formula)
            exprs_solucion.append(expr)
        except ValueError as exc:
            raise RuntimeError(
                f"Fórmula solución inválida en argumento: '{formula}'. "
                f"Error: {exc}. Esto es un bug en la carga del ejercicio."
            ) from exc

    # Si hay errores de parseo en el estudiante, devolver sin tabla
    if hay_error:
        return {
            "correcto": False,
            "errores_parse": errores_parse,
            "tabla_argumento": None,
            "es_valido": None,
            "juicio_estudiante_valido": juicio_valido,
            "formulas_ok": False,
        }

    # --- Construir tabla combinada de la solución ---
    # Recolectar todas las variables libres de todas las fórmulas de la solución
    todas_variables = set()
    for expr in exprs_solucion:
        todas_variables.update(expr.free_symbols)
    variables_ordenadas = sorted(todas_variables, key=lambda s: s.name)

    # Separar premisas y conclusión de la solución (en orden de aparición)
    premisas_sol = [
        exprs_solucion[i]
        for i, e in enumerate(enunciados_solucion)
        if e.get('tipo') == 'premisa'
    ]
    conclusion_sol = next(
        (exprs_solucion[i] for i, e in enumerate(enunciados_solucion)
         if e.get('tipo') == 'conclusion'),
        None,
    )

    # Construir tabla del argumento (2^n filas)
    tabla_argumento = []
    for valores in cartesian_product([True, False], repeat=len(variables_ordenadas)):
        asignacion = dict(zip(variables_ordenadas, valores))
        sub_items = list(asignacion.items())
        fila = {v.name: val for v, val in asignacion.items()}

        # Evaluar cada premisa
        resultados_premisas = []
        for idx, expr_premisa in enumerate(premisas_sol):
            res = bool(expr_premisa.subs(sub_items))
            fila[f'P{idx + 1}'] = res
            resultados_premisas.append(res)

        # Evaluar conclusión
        res_conclusion = bool(conclusion_sol.subs(sub_items)) if conclusion_sol is not None else True
        fila['C'] = res_conclusion

        # valido_fila: False solo cuando todas las premisas son V y la conclusión es F
        todas_premisas_v = all(resultados_premisas)
        fila['valido_fila'] = not (todas_premisas_v and not res_conclusion)

        tabla_argumento.append(fila)

    es_valido = all(fila['valido_fila'] for fila in tabla_argumento)

    # --- Matching: verificar que las fórmulas del estudiante coincidan ---
    # El renombramiento de variables debe ser global para todo el argumento.
    # Si E representa lo mismo que P en una premisa, debe conservar ese rol en
    # la conclusión y también al corregir la tabla completada.
    todas_variables_est = set()
    for expr in exprs_estudiante:
        todas_variables_est.update(expr.free_symbols)
    variables_estudiante_ordenadas = sorted(todas_variables_est, key=lambda s: s.name)

    def _columna(expr, variables):
        return [
            bool(expr.subs(list(zip(variables, valores))))
            for valores in cartesian_product([True, False], repeat=len(variables))
        ]

    def _equivalentes_con_mapeo(expr_est, expr_sol, mapeo_est_a_sol):
        expr_est_renombrada = expr_est.xreplace(mapeo_est_a_sol)
        return _columna(expr_est_renombrada, variables_ordenadas) == _columna(expr_sol, variables_ordenadas)

    # Agrupar índices del estudiante por tipo
    est_indices_por_tipo = {}
    for i, e in enumerate(enunciados_estudiante):
        tipo = e.get('tipo', 'premisa')
        est_indices_por_tipo.setdefault(tipo, []).append(i)

    def _buscar_matching_global():
        if len(enunciados_estudiante) != len(enunciados_solucion):
            return False, None
        if len(variables_estudiante_ordenadas) != len(variables_ordenadas):
            return False, None

        for perm in all_permutations(variables_ordenadas):
            mapeo = dict(zip(variables_estudiante_ordenadas, perm))
            indices_usados = set()
            ok = True

            for i_sol, e_sol in enumerate(enunciados_solucion):
                tipo_sol = e_sol.get('tipo', 'premisa')
                expr_sol = exprs_solucion[i_sol]

                encontrado = False
                for i_est in est_indices_por_tipo.get(tipo_sol, []):
                    if i_est in indices_usados:
                        continue
                    expr_est = exprs_estudiante[i_est]
                    if _equivalentes_con_mapeo(expr_est, expr_sol, mapeo):
                        indices_usados.add(i_est)
                        encontrado = True
                        break

                if not encontrado:
                    ok = False
                    break

            if ok:
                return True, mapeo

        return False, None

    formulas_ok, _mapeo_variables = _buscar_matching_global()

    # --- Generar tabla completa con subcolumnas (para columnas_tabla y corrección) ---
    tabla_sol_con_sub, _etiquetas_sol, columnas_enunciados_sol = _generar_tabla_con_subcolumnas(
        exprs_solucion, enunciados_solucion, variables_ordenadas
    )
    tabla_est_con_sub, _etiquetas_est, columnas_enunciados_est = _generar_tabla_con_subcolumnas(
        exprs_estudiante, enunciados_estudiante, variables_estudiante_ordenadas
    )
    tabla_con_sub = tabla_est_con_sub if formulas_ok else tabla_sol_con_sub
    variables_referencia = variables_estudiante_ordenadas if formulas_ok else variables_ordenadas
    columnas_enunciados = columnas_enunciados_est if formulas_ok else columnas_enunciados_sol

    # Todas las columnas en orden: variables primero, luego fórmulas.
    # El estudiante debe completar TODAS (incluyendo variables).
    variables_tabla = [v.name for v in variables_referencia]
    columnas_formula = [k for k in (tabla_con_sub[0].keys() if tabla_con_sub else [])
                        if k not in variables_tabla]
    # columnas_tabla = todas las que el estudiante debe llenar (variables + fórmulas)
    columnas_tabla = variables_tabla + columnas_formula
    # tabla_canonica: tabla correcta completa (variables + fórmulas) — para corrección
    tabla_canonica = [
        {col: fila[col] for col in columnas_tabla}
        for fila in tabla_con_sub
    ]

    # --- Verificar tabla ingresada por el estudiante ---
    tabla_ok = True
    enunciados_ok = True

    if tabla_estudiante is not None and not hay_error and formulas_ok:
        # Ordenar ambas tablas por valores de variables para que la comparación
        # sea independiente del orden de filas que eligió el estudiante.
        if variables_tabla:
            sort_fn = lambda row: tuple(not row.get(v, True) for v in variables_tabla)
            tabla_est_ord = sorted(tabla_estudiante, key=sort_fn)
            tabla_sol_ord = sorted(tabla_con_sub, key=sort_fn)
        else:
            tabla_est_ord = list(tabla_estudiante)
            tabla_sol_ord = list(tabla_con_sub)

        if len(tabla_est_ord) != len(tabla_sol_ord):
            tabla_ok = False

        # A) Cada columna esperada debe estar y coincidir con la tabla correcta
        # para las formulas/letras efectivamente usadas por lx estudiante.
        for i, fila_sol in enumerate(tabla_sol_ord):
            if i >= len(tabla_est_ord):
                tabla_ok = False
                break
            fila_est = tabla_est_ord[i]
            for col in columnas_tabla:
                if col not in fila_est or fila_est[col] != fila_sol[col]:
                    tabla_ok = False

        # B) Las columnas de los enunciados completos deben coincidir con la solución
        for col in columnas_enunciados:
            col_est = [f.get(col) for f in tabla_est_ord]
            col_sol = [f.get(col) for f in tabla_sol_ord]
            if col_est != col_sol:
                enunciados_ok = False

    correcto = formulas_ok and tabla_ok and enunciados_ok and (juicio_valido == es_valido)

    return {
        "correcto": correcto,
        "errores_parse": errores_parse,
        "tabla_argumento": tabla_argumento,
        "tabla_con_subcolumnas": tabla_con_sub,
        "columnas_tabla": columnas_tabla,
        "columnas_enunciados": columnas_enunciados,
        "variables_tabla": variables_tabla,
        "tabla_canonica": tabla_canonica,
        "es_valido": es_valido,
        "juicio_estudiante_valido": juicio_valido,
        "formulas_ok": formulas_ok,
        "tabla_ok": tabla_ok,
        "enunciados_ok": enunciados_ok,
    }


def distancia_semantica(formula_a: str, formula_b: str) -> int | None:
    """Número de filas donde el resultado difiere entre dos fórmulas.

    Cuando ambas fórmulas tienen el mismo conjunto de variables, la distancia
    es el conteo directo de filas discordantes (ordenadas canónicamente).
    Cuando tienen el mismo número de variables pero nombres distintos, se
    prueba la permutación de mínima distancia y se devuelve ese mínimo.
    En cualquier otro caso (distinto número de variables, error de parseo)
    se devuelve ``None``.

    Esta función es auxiliar para :mod:`motor.clasificador` y para el
    análisis de convergencia de :mod:`analiticas.calculos`.

    Args:
        formula_a: primera fórmula en ASCII normalizado.
        formula_b: segunda fórmula en ASCII normalizado.

    Returns:
        Entero ≥ 0 si las fórmulas son comparables, ``None`` en caso contrario.

    Examples:
        Mismas variables, 1 fila distinta::

            >>> distancia_semantica('p & q', 'p | q')
            2

        Distinto número de variables → None::

            >>> distancia_semantica('p', 'p & q') is None
            True
    """
    try:
        expr_a = parsear(formula_a)
        expr_b = parsear(formula_b)
    except (ValueError, Exception):
        return None

    vars_a = frozenset(v.name for v in expr_a.free_symbols)
    vars_b = frozenset(v.name for v in expr_b.free_symbols)

    if len(vars_a) != len(vars_b):
        return None

    if not vars_a:
        # Fórmulas sin variables libres (simplificadas a True/False)
        return 0 if bool(expr_a) == bool(expr_b) else 1

    vars_a_sym = sorted(expr_a.free_symbols, key=lambda s: s.name)
    vars_b_sym = sorted(expr_b.free_symbols, key=lambda s: s.name)
    n = len(vars_b_sym)

    # Columna canónica de B (base de comparación)
    col_b = [
        bool(expr_b.subs(list(zip(vars_b_sym, vals))))
        for vals in cartesian_product([True, False], repeat=n)
    ]

    if vars_a == vars_b:
        # Mismas variables: comparación directa con orden canónico
        col_a = [
            bool(expr_a.subs(list(zip(vars_a_sym, vals))))
            for vals in cartesian_product([True, False], repeat=n)
        ]
        return sum(a != b for a, b in zip(col_a, col_b))

    # Mismo número, distintos nombres: probar todas las permutaciones
    min_dist = None
    for perm in all_permutations(vars_a_sym):
        col_a = [
            bool(expr_a.subs(list(zip(perm, vals))))
            for vals in cartesian_product([True, False], repeat=n)
        ]
        dist = sum(a != b for a, b in zip(col_a, col_b))
        if min_dist is None or dist < min_dist:
            min_dist = dist
            if min_dist == 0:
                break  # no puede mejorar
    return min_dist


def verificar_determinacion(
    formula_estudiante: str,
    valores_dict_estudiante: dict,
    valor_asignado_estudiante,
    formula_solucion: str,
    valores_dict_solucion: dict,
) -> dict:
    """Verifica la respuesta de un ejercicio de determinación de valor de verdad.

    El ejercicio consiste en que el estudiante:
    1. Construye su propio diccionario asignando un valor de verdad a cada
       variable proposicional simple.
    2. Escribe la fórmula que formaliza el enunciado propuesto por el docente.
    3. Determina **manualmente** el valor de verdad de su fórmula en base a
       los valores de su diccionario.

    La corrección tiene **dos controles independientes**:

    A. **Consistencia interna**: ¿el valor que asignó el estudiante coincide
       con el resultado de evaluar su propia fórmula usando su propio
       diccionario?
    B. **Coincidencia con la solución**: ¿el valor calculado de la fórmula del
       estudiante coincide con el valor calculado de la fórmula solución del
       docente?

    Solo si *ambos* controles pasan, ``correcto`` es ``True``.

    Args:
        formula_estudiante: fórmula enviada por el estudiante, en ASCII
            normalizado.
        valores_dict_estudiante: ``{"A": True, "B": False}`` — valor de verdad
            asignado por el estudiante a cada variable de su diccionario.
        valor_asignado_estudiante: ``True`` o ``False`` — valor de verdad que
            el estudiante declaró para su fórmula. ``None`` si no lo indicó.
        formula_solucion: fórmula solución del docente, en ASCII normalizado.
        valores_dict_solucion: ``{"A": True, "B": False}`` — valores de verdad
            del diccionario del docente.

    Returns:
        ``dict`` con las siguientes claves:

        ``correcto`` (:class:`bool`)
            ``True`` si y solo si la fórmula parseó correctamente, la
            consistencia interna es correcta y el resultado coincide con
            la solución del docente.

        ``error_parse`` (:class:`str` or ``None``)
            Mensaje de error si la fórmula del estudiante no pudo parsearse.

        ``valor_calculado_estudiante`` (:class:`bool` or ``None``)
            Resultado de evaluar la fórmula del estudiante con su diccionario.
            ``None`` si hubo error de parseo o variables no definidas.

        ``valor_solucion`` (:class:`bool`)
            Resultado de evaluar la fórmula solución del docente.

        ``consistente`` (:class:`bool` or ``None``)
            ``True`` si ``valor_asignado_estudiante == valor_calculado_estudiante``.
            ``None`` si no pudo calcularse.

        ``coincide_solucion`` (:class:`bool` or ``None``)
            ``True`` si ``valor_calculado_estudiante == valor_solucion``.
            ``None`` si no pudo calcularse.

    Raises:
        RuntimeError: si la fórmula solución del docente no pudo parsearse
            o tiene variables sin valor asignado. Es un bug del sistema.
    """
    # --- Evaluar fórmula solución del docente (errores = bug del sistema) ---
    try:
        expr_solucion = parsear(formula_solucion)
    except ValueError as e:
        raise RuntimeError(
            f"La fórmula solución del ejercicio no es válida: {e}. "
            "Esto es un error en la carga del ejercicio y debe corregirse."
        ) from e

    vars_solucion = {s.name for s in expr_solucion.free_symbols}
    vars_faltantes_sol = vars_solucion - set(valores_dict_solucion.keys())
    if vars_faltantes_sol:
        raise RuntimeError(
            f"Las variables {sorted(vars_faltantes_sol)} de la fórmula solución no tienen "
            "valor asignado en el diccionario del docente. Error en la carga del ejercicio."
        )

    valor_solucion = _evaluar_con_valores(expr_solucion, valores_dict_solucion)

    # --- Parsear fórmula del estudiante ---
    try:
        validar_parentesis_en_operaciones_mixtas(formula_estudiante)
        expr_estudiante = parsear(formula_estudiante)
    except ValueError as e:
        detalle = str(e)
        mensaje = f'La fórmula ingresada no es una fórmula bien formada (fbf). ({detalle})'
        return {
            "correcto": False,
            "error_parse": mensaje,
            "valor_calculado_estudiante": None,
            "valor_solucion": valor_solucion,
            "consistente": None,
            "coincide_solucion": None,
        }

    # --- Evaluar fórmula del estudiante ---
    vars_estudiante = {s.name for s in expr_estudiante.free_symbols}
    vars_faltantes_est = vars_estudiante - set(valores_dict_estudiante.keys())
    if vars_faltantes_est:
        # Variables en la fórmula sin valor en el diccionario: error del estudiante
        return {
            "correcto": False,
            "error_parse": (
                f'La fórmula usa las variables {sorted(vars_faltantes_est)} '
                'que no tienen valor de verdad asignado en tu diccionario.'
            ),
            "valor_calculado_estudiante": None,
            "valor_solucion": valor_solucion,
            "consistente": None,
            "coincide_solucion": None,
        }

    valor_calculado = _evaluar_con_valores(expr_estudiante, valores_dict_estudiante)

    # --- Controles ---
    consistente = (valor_asignado_estudiante is not None) and (bool(valor_asignado_estudiante) == valor_calculado)
    coincide_solucion = (valor_calculado == valor_solucion)
    correcto = consistente and coincide_solucion

    return {
        "correcto": correcto,
        "error_parse": None,
        "valor_calculado_estudiante": valor_calculado,
        "valor_solucion": valor_solucion,
        "consistente": consistente,
        "coincide_solucion": coincide_solucion,
    }
