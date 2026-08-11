# motor/parser.py
"""Parser de fórmulas proposicionales en notación Copi.

Este módulo implementa un **tokenizador** y un **parser de descenso recursivo**
para fórmulas de lógica proposicional. Es el punto de entrada al motor lógico:
convierte una cadena de texto en una expresión :mod:`sympy` que puede ser
evaluada o manipulada.

Sintaxis aceptada
-----------------
La **notación primaria** es la de Irving Copi (*Introduction to Logic*), que
es la que usan los cursos IPC/CBC-UBA. Se aceptan además alternativas ASCII
equivalentes para facilitar la entrada por teclado estándar.

+----------+----------+--------------------+---------------------+
| Copi     | ASCII alt | Conectivo         | Ejemplo             |
+==========+==========+====================+=====================+
| ``~``    | ``~``    | Negación           | ``~p``              |
+----------+----------+--------------------+---------------------+
| ``·``    | ``&`` / ``.`` | Conjunción   | ``p · q``           |
+----------+----------+--------------------+---------------------+
| ``∨``    | ``|``    | Disyunción         | ``p ∨ q``           |
+----------+----------+--------------------+---------------------+
| ``⊃``    | ``->``   | Condicional        | ``p ⊃ q``           |
+----------+----------+--------------------+---------------------+
| ``≡``    | ``<->``  | Bicondicional      | ``p ≡ q``           |
+----------+----------+--------------------+---------------------+

Las **variables** son identificadores que empiezan con letra: ``p``, ``q``,
``p1``, ``r_aux``. Se distinguen mayúsculas de minúsculas.

Se permiten espacios en cualquier posición. La agrupación se hace con paréntesis
``()``.

Precedencia (de mayor a menor binding)
---------------------------------------
``~``  >  ``·``  >  ``∨``  >  ``⊃``  >  ``≡``

El condicional ``⊃`` (o ``->``) es **right-associative**:
``p ⊃ q ⊃ r``  se parsea como  ``p ⊃ (q ⊃ r)``.

El bicondicional ``≡`` es left-associative.

Entrada mixta
-------------
El motor acepta indistintamente símbolos Copi y sus equivalentes ASCII.
Se puede escribir ``p ⊃ (q · r)`` o ``p -> (q & r)`` o mezclarlos.
Si se recibe un símbolo no reconocido (``∧``, ``→``, ``↔``, etc.),
el tokenizador lanza :exc:`ValueError` con un mensaje que sugiere el
equivalente Copi correcto.

Notas de implementación
-----------------------
El tokenizador es un escáner lineal con lookahead de 3 caracteres (necesario
para distinguir ``<->`` de ``<`` y ``->`` de ``-``). El parser implementa
la gramática::

    formula      := iff
    iff          := implies ('≡' implies)*        [o '<->']
    implies      := disyuncion ('⊃' implies)?     [o '->', right-associative]
    disyuncion   := conjuncion ('∨' conjuncion)*  [o '|']
    conjuncion   := negacion ('·' negacion)*      [o '&' o '.']
    negacion     := '~' negacion | atomo
    atomo        := '(' formula ')' | VAR

No se usan expresiones regulares en el parser para garantizar mensajes de
error precisos y facilitar la extensión futura.
"""

import re
from sympy import Symbol
from sympy.logic.boolalg import And, Or, Not, Implies, Equivalent

# ---------------------------------------------------------------------------
# Tokenizador
# ---------------------------------------------------------------------------

# Representación canónica de cada tipo de token para mensajes de error.
# Se muestra el símbolo Copi primero.
_TK = {
    'IFF':     '≡',
    'IMPLIES': '⊃',
    'AND':     '·',
    'OR':      '∨',
    'NEG':     '~',
    'LPAREN':  '(',
    'RPAREN':  ')',
}
_VAR_RE = re.compile(r'[A-Za-z]\w*')


def _tokenize(formula: str) -> list[tuple[str, str | None]]:
    """Convierte una cadena en una lista de tokens.

    Acepta tanto la notación Copi (``·``, ``∨``, ``⊃``, ``≡``) como los
    equivalentes ASCII (``&``, ``.``, ``|``, ``->``, ``<->``). Ambas pueden
    mezclarse en la misma fórmula.

    Args:
        formula: fórmula en notación Copi o ASCII (puede contener espacios).

    Returns:
        Lista de tuplas ``(tipo, valor)``. El último token es siempre
        ``('EOF', None)``.

    Raises:
        ValueError: si se encuentra un carácter no reconocido, con un mensaje
            que sugiere el símbolo Copi equivalente cuando corresponde.

    Examples:
        Notación Copi::

            >>> _tokenize('p ⊃ q')
            [('VAR', 'p'), ('IMPLIES', '⊃'), ('VAR', 'q'), ('EOF', None)]

        Alternativa ASCII::

            >>> _tokenize('p -> q')
            [('VAR', 'p'), ('IMPLIES', '->'), ('VAR', 'q'), ('EOF', None)]
    """
    tokens: list[tuple[str, str | None]] = []
    pos = 0
    n = len(formula)

    while pos < n:
        if formula[pos].isspace():
            pos += 1
            continue

        # ASCII multi-char: <-> debe evaluarse antes que -> para no consumir
        # sólo los dos primeros chars.
        if formula[pos:pos + 3] == '<->':
            tokens.append(('IFF', '<->'))
            pos += 3
        elif formula[pos:pos + 2] == '->':
            tokens.append(('IMPLIES', '->'))
            pos += 2

        # Símbolos Copi (Unicode)
        elif formula[pos] == '\u2261':   # ≡ IDENTICAL TO — bicondicional Copi
            tokens.append(('IFF', '\u2261'))
            pos += 1
        elif formula[pos] == '\u2283':   # ⊃ SUPERSET OF — condicional Copi
            tokens.append(('IMPLIES', '\u2283'))
            pos += 1
        elif formula[pos] == '\u00b7':   # · MIDDLE DOT — conjunción Copi
            tokens.append(('AND', '\u00b7'))
            pos += 1
        elif formula[pos] == '\u2228':   # ∨ LOGICAL OR — disyunción Copi
            tokens.append(('OR', '\u2228'))
            pos += 1

        # Símbolos ASCII equivalentes (alternativas aceptadas)
        elif formula[pos] == '&' or formula[pos] == '.':
            tokens.append(('AND', '&'))
            pos += 1
        elif formula[pos] == '|':
            tokens.append(('OR', '|'))
            pos += 1
        elif formula[pos] == '~':
            tokens.append(('NEG', '~'))
            pos += 1
        elif formula[pos] == '(':
            tokens.append(('LPAREN', '('))
            pos += 1
        elif formula[pos] == ')':
            tokens.append(('RPAREN', ')'))
            pos += 1

        # Variables
        elif _VAR_RE.match(formula[pos]):
            m = _VAR_RE.match(formula[pos:])
            tokens.append(('VAR', m.group()))
            pos += len(m.group())

        # Caracteres no reconocidos: sugerir equivalente Copi
        else:
            char = formula[pos]
            sugerencia = {
                '\u2227': "Usar '\u00b7' para la conjunci\u00f3n (notaci\u00f3n Copi).",
                '\u2192': "Usar '\u2283' o '->' para el condicional.",
                '\u21d2': "Usar '\u2283' o '->' para el condicional.",
                '\u2194': "Usar '\u2261' para el bicondicional.",
                '\u21d4': "Usar '\u2261' para el bicondicional.",
                '\u00ac': "Usar '~' para la negaci\u00f3n.",
            }.get(char, "")
            msg = f"Car\u00e1cter no reconocido: '{char}'"
            if sugerencia:
                msg += f" \u2014 {sugerencia}"
            raise ValueError(msg)

    tokens.append(('EOF', None))
    return tokens


# ---------------------------------------------------------------------------
# Parser de descenso recursivo
# ---------------------------------------------------------------------------

class _Parser:
    """Parser de descenso recursivo para fórmulas proposicionales.

    Implementa la gramática completa con precedencia estándar de lógica
    proposicional (notación Copi). No está destinado a uso externo;
    usar :func:`parsear`.

    Args:
        tokens: lista de tokens producida por :func:`_tokenize`.
    """

    def __init__(self, tokens: list[tuple[str, str | None]]):
        self.tokens = tokens
        self.pos = 0

    # ---- helpers -----------------------------------------------------------

    def _peek(self) -> str:
        """Devuelve el tipo del token actual sin consumirlo."""
        return self.tokens[self.pos][0]

    def _consume(self, expected: str | None = None) -> tuple[str, str | None]:
        """Consume y devuelve el token actual.

        Args:
            expected: tipo de token esperado. Si no coincide, lanza
                :exc:`ValueError` con mensaje descriptivo.

        Returns:
            Tupla ``(tipo, valor)`` del token consumido.

        Raises:
            ValueError: si ``expected`` no es ``None`` y el tipo del token
                actual no coincide.
        """
        tok = self.tokens[self.pos]
        if expected is not None and tok[0] != expected:
            got = tok[1] if tok[1] is not None else 'fin de fórmula'
            raise ValueError(
                f"Se esperaba '{_TK.get(expected, expected)}', "
                f"pero se encontró '{got}'."
            )
        self.pos += 1
        return tok

    # ---- reglas gramaticales -----------------------------------------------

    def parse(self):
        """Punto de entrada del parser.

        Returns:
            Expresión :mod:`sympy` que representa la fórmula completa.

        Raises:
            ValueError: si quedan tokens sin consumir tras parsear la fórmula.
        """
        result = self._formula()
        if self._peek() != 'EOF':
            tok = self.tokens[self.pos]
            raise ValueError(
                f"Token inesperado '{tok[1]}' al final de la fórmula."
            )
        return result

    def _formula(self):
        return self._iff()

    def _iff(self):
        """Regla: iff := implies ('≡' implies)*  [left-associative, acepta '<->']."""
        left = self._implies()
        while self._peek() == 'IFF':
            self._consume('IFF')
            right = self._implies()
            left = Equivalent(left, right)
        return left

    def _implies(self):
        """Regla: implies := disyuncion ('⊃' implies)?  [right-associative, acepta '->']."""
        left = self._disyuncion()
        if self._peek() == 'IMPLIES':
            self._consume('IMPLIES')
            right = self._implies()      # right-associative: llamada recursiva
            return Implies(left, right)
        return left

    def _disyuncion(self):
        """Regla: disyuncion := conjuncion ('∨' conjuncion)*  [acepta '|']."""
        left = self._conjuncion()
        while self._peek() == 'OR':
            self._consume('OR')
            right = self._conjuncion()
            left = Or(left, right)
        return left

    def _conjuncion(self):
        """Regla: conjuncion := negacion ('·' negacion)*  [acepta '&']."""
        left = self._negacion()
        while self._peek() == 'AND':
            self._consume('AND')
            right = self._negacion()
            left = And(left, right)
        return left

    def _negacion(self):
        """Regla: negacion := '~' negacion | atomo  [right-associative, permite ~~p]."""
        if self._peek() == 'NEG':
            self._consume('NEG')
            operand = self._negacion()   # recursivo: soporta ~~p, ~~~p, etc.
            return Not(operand)
        return self._atomo()

    def _atomo(self):
        """Regla: atomo := '(' formula ')' | VAR.

        Raises:
            ValueError: si no se encuentra una variable ni un paréntesis de apertura.
        """
        if self._peek() == 'LPAREN':
            self._consume('LPAREN')
            expr = self._formula()
            if self._peek() != 'RPAREN':
                raise ValueError("Paréntesis de cierre ')' faltante.")
            self._consume('RPAREN')
            return expr

        if self._peek() == 'VAR':
            tok = self._consume('VAR')
            return Symbol(tok[1])

        tok = self.tokens[self.pos]
        got = tok[1] if tok[1] is not None else 'fin de fórmula'
        raise ValueError(
            f"Se esperaba una variable o '(', pero se encontró '{got}'."
        )


# ---------------------------------------------------------------------------
# Interfaz pública
# ---------------------------------------------------------------------------

def normalizar_simbolos(formula: str) -> str:
    """Normaliza variantes frecuentes de conectivos a notación Copi.

    Mantiene consistencia con el flujo estudiantil del frontend, que admite
    variantes de teclado/copy-paste (``¬``, ``∧``, ``→``, ``↔``) y las
    transforma antes de enviar al backend.

    Args:
        formula: fórmula original escrita por la persona usuaria.

    Returns:
        Cadena con símbolos normalizados:

        - ``¬`` → ``~``
        - ``∧`` → ``·``
        - ``→``, ``⇒``, ``=>`` → ``⊃``
        - ``↔``, ``⇔`` → ``≡``

        Los conectivos ASCII ya soportados por el parser (``->``, ``<->``,
        ``&``, ``.``, ``|``) se preservan.
    """
    # Reemplazar 'v'/'V' como alias de disyunción:
    # - caso aislado: "v" o "V"
    # - caso infijo pegado a operandos: "JvM", ")V(", "~pvq"
    # Se evita transformar dentro de nombres largos (ej. "vuelta").
    # 'V' mayúscula está reservada en el frontend (no puede usarse como variable)
    # para evitar exactamente esta ambigüedad; el backend la normaliza igual.
    formula = re.sub(r'(?<![A-Za-z0-9_])[vV](?![A-Za-z0-9_])', '\u2228', formula)
    formula = re.sub(
        r'(?<=[A-Za-z0-9_)\]])[vV](?=[A-Za-z0-9_(~\[])',
        '\u2228',
        formula,
    )
    return (
        formula
        .replace('\u00ac', '~')
        .replace('\u2227', '\u00b7')
        .replace('\u2192', '\u2283')
        .replace('\u21d2', '\u2283')
        .replace('=>', '\u2283')
        .replace('\u2194', '\u2261')
        .replace('\u21d4', '\u2261')
    )

def extraer_variables_en_orden(formula: str) -> list[str]:
    """Devuelve las variables de la fórmula en orden de primera aparición.

    Trabaja sobre el stream de tokens, antes de que sympy reordene los args
    de Or/And. Es la única fuente fiable para preservar el orden escrito
    por la persona usuaria.
    """
    tokens = _tokenize(formula.strip())
    seen: set[str] = set()
    result: list[str] = []
    for tipo, valor in tokens:
        if tipo == 'VAR' and valor not in seen:
            seen.add(valor)
            result.append(valor)
    return result


def parsear(formula: str):
    """Parsea una fórmula proposicional en notación Copi o ASCII equivalente.

    Convierte la cadena de texto en una expresión :mod:`sympy.logic.boolalg`
    que puede ser evaluada o usada para generar tablas de verdad.

    Acepta la notación Copi (``·``, ``∨``, ``⊃``, ``≡``, ``~``) y las
    alternativas ASCII (``&``, ``.``, ``|``, ``->``, ``<->``). Ambas pueden
    mezclarse. La precedencia es:
    ``~`` > ``·`` > ``∨`` > ``⊃`` > ``≡``

    Args:
        formula: cadena en notación Copi o ASCII normalizado. Se admiten
            espacios en cualquier posición. Ejemplos válidos::

                'p ⊃ q'
                '~p · (q ∨ r)'
                'p ≡ (~p ∨ q)'
                '(p ⊃ q) · (q ⊃ r) ⊃ (p ⊃ r)'
                'p -> q'          # alternativa ASCII para ⊃

    Returns:
        Expresión :class:`sympy.Basic` (subtipo de
        :mod:`sympy.logic.boolalg`) que representa la fórmula.
        El tipo concreto depende del conectivo principal:
        :class:`~sympy.logic.boolalg.And`,
        :class:`~sympy.logic.boolalg.Or`,
        :class:`~sympy.logic.boolalg.Not`,
        :class:`~sympy.logic.boolalg.Implies`,
        :class:`~sympy.logic.boolalg.Equivalent`, o
        :class:`~sympy.core.symbol.Symbol` para átomos.

    Raises:
        ValueError: si la fórmula está vacía, contiene caracteres no
            reconocidos, o tiene errores sintácticos (paréntesis sin
            cerrar, conectivo sin operando, etc.). El mensaje de error
            es legible y apto para mostrarse al estudiante, con
            sugerencias de normalización para símbolos no soportados
            (``∧``, ``→``, ``↔``).

    Examples:
        Notación Copi::

            >>> from motor.parser import parsear
            >>> parsear('p ⊃ q')
            Implies(p, q)

        Alternativa ASCII::

            >>> parsear('p -> q')
            Implies(p, q)

        Mixto::

            >>> parsear('~p · (q ∨ r)')
            And(Not(p), Or(q, r))

        Error de parseo::

            >>> parsear('p ∧ q')
            ValueError: Carácter no reconocido: '∧' — Usar '·' para la conjunción (notación Copi).

    Note:
        El parser acepta directamente tanto los símbolos Copi como sus
        equivalentes ASCII. No se requiere pre-normalización por parte del
        frontend, aunque el frontend puede normalizar variantes adicionales
        (``→``, ``↔``, etc.) antes de llamar al motor.
    """
    formula = formula.strip()
    if not formula:
        raise ValueError("La fórmula está vacía.")

    tokens = _tokenize(formula)
    parser = _Parser(tokens)
    return parser.parse()


def validar_parentesis_en_operaciones_mixtas(formula: str) -> None:
    """Valida que AND y OR sean estrictamente binarios y no se mezclen sin paréntesis.

    Aplica dos restricciones pedagógicas en cada nivel de paréntesis:

    1. **Binariedad**: la conjunción (·) y la disyunción (∨) solo pueden
       conectar dos términos por nivel. Una cadena ``A · B · C`` requiere
       agrupación explícita: ``(A · B) · C`` o ``A · (B · C)``.

    2. **No mezcla**: si aparecen conectivos binarios de más de un tipo en el
       mismo nivel (p.ej. ``·`` y ``∨``), la fórmula se rechaza. Escribir
       ``(A · B) ∨ C`` o ``A · (B ∨ C)``.

    Args:
        formula: fórmula escrita por la persona usuaria.

    Raises:
        ValueError: si en algún nivel de paréntesis se detecta una conjunción
            o disyunción encadenada, o mezcla de conectivos sin agrupar.
    """
    tokens = _tokenize(formula.strip())[:-1]

    # Cada elemento del stack es un dict {tipo: count} de conectivos binarios
    # usados dentro del scope delimitado por ese par de paréntesis (nivel raíz
    # incluido). Al cerrar un ')' se valida y descarta el scope interior.
    stack: list[dict] = [{}]

    def _validar_scope(scope: dict) -> None:
        total = sum(scope.values())
        if total <= 1:
            return
        tipos = [t for t, c in scope.items() if c > 0]
        if len(tipos) == 1:
            tipo = tipos[0]
            if tipo == 'AND':
                raise ValueError(
                    "La conjunción (·) solo puede conectar dos términos por nivel. "
                    "Agrupá con paréntesis: '(A · B) · C' o 'A · (B · C)'."
                )
            if tipo == 'OR':
                raise ValueError(
                    "La disyunción (∨) solo puede conectar dos términos por nivel. "
                    "Agrupá con paréntesis: '(A ∨ B) ∨ C' o 'A ∨ (B ∨ C)'."
                )
            raise ValueError(
                "Cada conectivo binario conecta exactamente dos términos. "
                "Agrupá con paréntesis explícitos."
            )
        raise ValueError(
            "Faltan paréntesis para desambiguar la fórmula. "
            "No mezcles conectivos binarios en el mismo nivel sin agrupar "
            "(ej.: '(A · B) ∨ C' o 'A · (B ∨ C)')."
        )

    for tipo, _ in tokens:
        if tipo == 'LPAREN':
            stack.append({})
            continue
        if tipo == 'RPAREN':
            _validar_scope(stack.pop())
            continue
        if tipo in {'AND', 'OR', 'IMPLIES', 'IFF'}:
            stack[-1][tipo] = stack[-1].get(tipo, 0) + 1

    _validar_scope(stack[-1])
