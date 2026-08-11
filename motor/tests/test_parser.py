# motor/tests/test_parser.py
"""
Tests para motor.parser.parsear()

Cubre:
  - Fórmulas atómicas (variables)
  - Cada conectivo en notación Copi
  - Cada conectivo en alternativa ASCII
  - Notación mixta Copi + ASCII
  - Agrupación con paréntesis
  - Precedencia correcta
  - Asociatividad derecha del condicional
  - Negación múltiple
  - Fórmulas con varias variables
  - Casos de error: vacía, token inesperado, paréntesis sin cerrar,
    conectivo sin operando, caracteres no soportados (∧, →, ↔)
"""

import pytest
from sympy import Symbol
from sympy.logic.boolalg import And, Or, Not, Implies, Equivalent

from motor.parser import normalizar_simbolos, parsear, validar_parentesis_en_operaciones_mixtas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sym(name):
    return Symbol(name)


def equiv_semantica(expr1, expr2, variables):
    """Compara dos expresiones sympy por equivalencia semántica (tabular)."""
    from itertools import product as cart
    for vals in cart([True, False], repeat=len(variables)):
        asig = dict(zip(variables, vals))
        if bool(expr1.subs(asig)) != bool(expr2.subs(asig)):
            return False
    return True


# ---------------------------------------------------------------------------
# Casos válidos — notación Copi
# ---------------------------------------------------------------------------

class TestNotacionCopi:
    """Verifica que los símbolos Copi son aceptados directamente por el parser."""

    def test_conjuncion_copi(self):
        p, q = sym('p'), sym('q')
        assert parsear('p \u00b7 q') == And(p, q)   # ·

    def test_disyuncion_copi(self):
        p, q = sym('p'), sym('q')
        assert parsear('p \u2228 q') == Or(p, q)    # ∨

    def test_condicional_copi(self):
        p, q = sym('p'), sym('q')
        assert parsear('p \u2283 q') == Implies(p, q)   # ⊃

    def test_bicondicional_copi(self):
        p, q = sym('p'), sym('q')
        assert parsear('p \u2261 q') == Equivalent(p, q)   # ≡

    def test_negacion_copi_igual_ascii(self):
        # ~ es el único símbolo de negación; sin cambio
        assert parsear('~p') == Not(sym('p'))

    def test_formula_compuesta_copi(self):
        # (p ⊃ q) · (q ⊃ r) ⊃ (p ⊃ r)  — silogismo hipotético
        p, q, r = sym('p'), sym('q'), sym('r')
        expr = parsear('(p \u2283 q) \u00b7 (q \u2283 r) \u2283 (p \u2283 r)')
        esperado = Implies(And(Implies(p, q), Implies(q, r)), Implies(p, r))
        assert equiv_semantica(expr, esperado, [p, q, r])

    def test_precedencia_copi(self):
        # ~p · q ⊃ r  debe ser  (~p · q) ⊃ r
        p, q, r = sym('p'), sym('q'), sym('r')
        expr = parsear('~p \u00b7 q \u2283 r')
        esperado = Implies(And(Not(p), q), r)
        assert equiv_semantica(expr, esperado, [p, q, r])

    def test_condicional_copi_right_assoc(self):
        # p ⊃ q ⊃ r  →  p ⊃ (q ⊃ r)
        p, q, r = sym('p'), sym('q'), sym('r')
        expr = parsear('p \u2283 q \u2283 r')
        esperado = Implies(p, Implies(q, r))
        assert equiv_semantica(expr, esperado, [p, q, r])

    def test_tabla_condicional_copi_conocida(self):
        # p ⊃ q: F solo cuando p=T, q=F
        tabla = [
            (True,  True,  True),
            (True,  False, False),
            (False, True,  True),
            (False, False, True),
        ]
        expr = parsear('p \u2283 q')
        p, q = sym('p'), sym('q')
        for pv, qv, esperado in tabla:
            assert bool(expr.subs({p: pv, q: qv})) == esperado

    def test_tabla_bicondicional_copi_conocida(self):
        tabla = [
            (True,  True,  True),
            (True,  False, False),
            (False, True,  False),
            (False, False, True),
        ]
        expr = parsear('p \u2261 q')
        p, q = sym('p'), sym('q')
        for pv, qv, esperado in tabla:
            assert bool(expr.subs({p: pv, q: qv})) == esperado

    def test_mixto_copi_ascii(self):
        # Mezcla: p ⊃ (q & r)  —  ⊃ Copi + & ASCII
        p, q, r = sym('p'), sym('q'), sym('r')
        expr = parsear('p \u2283 (q & r)')
        esperado = Implies(p, And(q, r))
        assert equiv_semantica(expr, esperado, [p, q, r])

    def test_arrow_alternativa_ascii_para_condicional(self):
        # -> y ⊃ deben producir el mismo resultado
        p, q = sym('p'), sym('q')
        assert parsear('p -> q') == parsear('p \u2283 q')

    def test_double_arrow_alternativa_ascii_para_bicondicional(self):
        p, q = sym('p'), sym('q')
        assert parsear('p <-> q') == parsear('p \u2261 q')


# ---------------------------------------------------------------------------
# Casos válidos — notación ASCII (compatibilidad hacia atrás)
# ---------------------------------------------------------------------------

class TestAtomico:
    def test_variable_simple(self):
        assert parsear('p') == sym('p')

    def test_variable_con_digito(self):
        assert parsear('p1') == sym('p1')

    def test_variable_mayuscula(self):
        assert parsear('P') == sym('P')

    def test_espacios_alrededor(self):
        assert parsear('  p  ') == sym('p')


class TestNegacion:
    def test_negacion_simple(self):
        assert parsear('~p') == Not(sym('p'))

    def test_negacion_doble(self):
        resultado = parsear('~~p')
        p = sym('p')
        for val in [True, False]:
            assert bool(resultado.subs(p, val)) == bool(p.subs(p, val))

    def test_negacion_triple(self):
        resultado = parsear('~~~p')
        p = sym('p')
        for val in [True, False]:
            assert bool(resultado.subs(p, val)) == bool(Not(p).subs(p, val))


class TestConjuncion:
    def test_conjuncion_ascii(self):
        assert parsear('p & q') == And(sym('p'), sym('q'))

    def test_conjuncion_ascii_punto(self):
        assert parsear('p . q') == And(sym('p'), sym('q'))

    def test_conjuncion_multiple(self):
        resultado = parsear('p & q & r')
        p, q, r = sym('p'), sym('q'), sym('r')
        esperado = And(p, q, r)
        assert equiv_semantica(resultado, esperado, [p, q, r])

    def test_conjuncion_mixta_ampersand_y_punto(self):
        resultado = parsear('p & q . r')
        p, q, r = sym('p'), sym('q'), sym('r')
        esperado = And(p, q, r)
        assert equiv_semantica(resultado, esperado, [p, q, r])


class TestDisyuncion:
    def test_disyuncion_ascii(self):
        assert parsear('p | q') == Or(sym('p'), sym('q'))


class TestNormalizacion:
    def test_normaliza_v_infixa_pegada(self):
        assert normalizar_simbolos('(JvM).~(J.M)') == '(J∨M).~(J.M)'

    def test_parsea_formula_con_v_infixa_normalizada(self):
        assert parsear(normalizar_simbolos('JvM')) == Or(sym('J'), sym('M'))


class TestCondicional:
    def test_condicional_ascii(self):
        p, q = sym('p'), sym('q')
        assert parsear('p -> q') == Implies(p, q)

    def test_condicional_right_associative(self):
        p, q, r = sym('p'), sym('q'), sym('r')
        resultado = parsear('p -> q -> r')
        esperado = Implies(p, Implies(q, r))
        assert equiv_semantica(resultado, esperado, [p, q, r])

    def test_tabla_condicional_conocida(self):
        tabla = [
            (True,  True,  True),
            (True,  False, False),
            (False, True,  True),
            (False, False, True),
        ]
        expr = parsear('p -> q')
        p, q = sym('p'), sym('q')
        for pv, qv, esperado in tabla:
            assert bool(expr.subs({p: pv, q: qv})) == esperado


class TestBicondicional:
    def test_bicondicional_ascii(self):
        p, q = sym('p'), sym('q')
        assert parsear('p <-> q') == Equivalent(p, q)

    def test_tabla_bicondicional_conocida(self):
        tabla = [
            (True,  True,  True),
            (True,  False, False),
            (False, True,  False),
            (False, False, True),
        ]
        expr = parsear('p <-> q')
        p, q = sym('p'), sym('q')
        for pv, qv, esperado in tabla:
            assert bool(expr.subs({p: pv, q: qv})) == esperado


class TestParentesis:
    def test_parentesis_cambia_precedencia(self):
        p, q = sym('p'), sym('q')
        sin_paren = parsear('~p & q')
        con_paren = parsear('~(p & q)')
        asig = {p: True, q: False}
        assert bool(sin_paren.subs(asig)) != bool(con_paren.subs(asig))

    def test_parentesis_anidados(self):
        resultado = parsear('((p))')
        assert resultado == sym('p')

    def test_condicional_con_parentesis_izquierdo(self):
        p, q, r = sym('p'), sym('q'), sym('r')
        izq = parsear('(p -> q) -> r')
        der = parsear('p -> (q -> r)')
        asig = {p: False, q: True, r: False}
        assert bool(izq.subs(asig)) != bool(der.subs(asig))


class TestPrecedencia:
    def test_neg_sobre_and(self):
        p, q = sym('p'), sym('q')
        expr = parsear('~p & q')
        assert not bool(expr.subs({p: True, q: True}))
        assert bool(expr.subs({p: False, q: True}))

    def test_and_sobre_or(self):
        p, q, r = sym('p'), sym('q'), sym('r')
        expr = parsear('p | q & r')
        assert not bool(expr.subs({p: False, q: True, r: False}))
        assert bool(expr.subs({p: False, q: True, r: True}))

    def test_or_sobre_implies(self):
        p, q, r = sym('p'), sym('q'), sym('r')
        expr = parsear('p -> q | r')
        esperado = Implies(p, Or(q, r))
        assert equiv_semantica(expr, esperado, [p, q, r])

    def test_implies_sobre_iff(self):
        p, q, r = sym('p'), sym('q'), sym('r')
        expr = parsear('p <-> q -> r')
        esperado = Equivalent(p, Implies(q, r))
        assert equiv_semantica(expr, esperado, [p, q, r])


# ---------------------------------------------------------------------------
# Casos de error
# ---------------------------------------------------------------------------

class TestErrores:
    def test_formula_vacia(self):
        with pytest.raises(ValueError, match="vac"):
            parsear('')

    def test_formula_solo_espacios(self):
        with pytest.raises(ValueError, match="vac"):
            parsear('   ')

    def test_caracter_inesperado(self):
        with pytest.raises(ValueError):
            parsear('p + q')

    def test_parentesis_sin_cerrar(self):
        with pytest.raises(ValueError):
            parsear('(p & q')

    def test_parentesis_de_mas(self):
        with pytest.raises(ValueError):
            parsear('p & q)')

    def test_conectivo_sin_operando_izquierdo(self):
        with pytest.raises(ValueError):
            parsear('& q')

    def test_conectivo_sin_operando_derecho(self):
        with pytest.raises(ValueError):
            parsear('p &')

    def test_condicional_sin_operando_derecho(self):
        with pytest.raises(ValueError):
            parsear('p ->')

    def test_unicode_wedge_no_es_copi(self):
        # ∧ (U+2227) NO es el símbolo Copi; Copi usa · (U+00B7)
        # Debe fallar con sugerencia de usar '·'
        with pytest.raises(ValueError, match="\u00b7"):
            parsear('p \u2227 q')

    def test_unicode_flecha_derecha_no_soportada(self):
        # → (U+2192) no se acepta; usar ⊃ o ->
        with pytest.raises(ValueError):
            parsear('p \u2192 q')

    def test_unicode_bicondicional_flecha_no_soportado(self):
        # ↔ (U+2194) no se acepta; usar ≡ o <->
        with pytest.raises(ValueError):
            parsear('p \u2194 q')


# ---------------------------------------------------------------------------
# Validación pedagógica: binariedad de AND/OR y no mezcla de conectivos
# ---------------------------------------------------------------------------

class TestValidarParentesisBinariedad:
    """AND y OR solo pueden conectar dos términos por nivel (criterio IPC)."""

    def test_conjuncion_encadenada_tres_terminos(self):
        with pytest.raises(ValueError, match="conjunci"):
            validar_parentesis_en_operaciones_mixtas('A · B · C')

    def test_conjuncion_encadenada_cuatro_terminos(self):
        with pytest.raises(ValueError, match="conjunci"):
            validar_parentesis_en_operaciones_mixtas('A & B & C & D')

    def test_disyuncion_encadenada_tres_terminos(self):
        with pytest.raises(ValueError, match="disyunci"):
            validar_parentesis_en_operaciones_mixtas('A ∨ B ∨ C')

    def test_disyuncion_encadenada_ascii(self):
        with pytest.raises(ValueError, match="disyunci"):
            validar_parentesis_en_operaciones_mixtas('A | B | C')

    def test_conjuncion_binaria_aceptada(self):
        validar_parentesis_en_operaciones_mixtas('A · B')   # no lanza

    def test_disyuncion_binaria_aceptada(self):
        validar_parentesis_en_operaciones_mixtas('A ∨ B')   # no lanza

    def test_conjuncion_agrupada_izquierda_aceptada(self):
        validar_parentesis_en_operaciones_mixtas('(A · B) · C')  # no lanza

    def test_conjuncion_agrupada_derecha_aceptada(self):
        validar_parentesis_en_operaciones_mixtas('A · (B · C)')  # no lanza

    def test_disyuncion_agrupada_izquierda_aceptada(self):
        validar_parentesis_en_operaciones_mixtas('(A ∨ B) ∨ C')  # no lanza

    def test_disyuncion_agrupada_derecha_aceptada(self):
        validar_parentesis_en_operaciones_mixtas('A ∨ (B ∨ C)')  # no lanza

    def test_cadena_anidada_dentro_de_parentesis(self):
        # '(A · B · C) ∨ D' — la cadena está dentro del subscope
        with pytest.raises(ValueError, match="conjunci"):
            validar_parentesis_en_operaciones_mixtas('(A · B · C) ∨ D')


class TestValidarParentesisMezcla:
    """Mezcla de conectivos distintos en el mismo nivel debe rechazarse."""

    def test_and_or_mismo_nivel(self):
        with pytest.raises(ValueError, match="[Mm]ezc|[Pp]ar"):
            validar_parentesis_en_operaciones_mixtas('A · B ∨ C')

    def test_and_or_mismo_nivel_ascii(self):
        with pytest.raises(ValueError, match="[Mm]ezc|[Pp]ar"):
            validar_parentesis_en_operaciones_mixtas('A & B | C')

    def test_and_or_agrupados_aceptados(self):
        validar_parentesis_en_operaciones_mixtas('(A · B) ∨ C')  # no lanza
        validar_parentesis_en_operaciones_mixtas('A · (B ∨ C)')  # no lanza

    def test_condicional_encadenado_rechazado(self):
        with pytest.raises(ValueError):
            validar_parentesis_en_operaciones_mixtas('p ⊃ q ⊃ r')

    def test_bicondicional_encadenado_rechazado(self):
        with pytest.raises(ValueError):
            validar_parentesis_en_operaciones_mixtas('p ≡ q ≡ r')

    def test_condicional_agrupado_aceptado(self):
        validar_parentesis_en_operaciones_mixtas('p ⊃ (q ⊃ r)')  # no lanza
        validar_parentesis_en_operaciones_mixtas('(p ⊃ q) ⊃ r')  # no lanza
