# motor/tests/test_verificador.py
"""
Tests para motor.verificador.verificar()

Cubre todos los casos edge del AGENTS.md:
  - Fórmulas correctas (equivalentes)
  - Fórmulas incorrectas (no equivalentes)
  - Error de parseo en respuesta del estudiante
  - Tautología vs. tautología (acepta por diseño)
  - Variables distintas, misma estructura (acepta por diseño)
  - Distinto número de variables (rechaza)
  - Bug en fórmula solución → RuntimeError
  - Estructura completa del dict de retorno
"""

import pytest
from motor.verificador import verificar, verificar_argumento


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def es_correcto(respuesta, solucion):
    return verificar(respuesta, solucion)['correcto']


# ---------------------------------------------------------------------------
# Casos correctos (equivalencia tabular)
# ---------------------------------------------------------------------------

class TestCorrectos:
    def test_identica(self):
        assert es_correcto('p -> q', 'p -> q')

    def test_equivalente_condicional_disyuncion(self):
        # p -> q  ≡  ~p | q
        assert es_correcto('~p | q', 'p -> q')

    def test_equivalente_demorgan_and(self):
        assert es_correcto('~p | ~q', '~(p & q)')

    def test_equivalente_demorgan_or(self):
        assert es_correcto('~p & ~q', '~(p | q)')

    def test_conmutativa_conjuncion(self):
        assert es_correcto('q & p', 'p & q')

    def test_conmutativa_disyuncion(self):
        assert es_correcto('q | p', 'p | q')

    def test_doble_negacion(self):
        assert es_correcto('~~p', 'p')

    def test_bicondicional_equivalencia(self):
        # p <-> q  ≡  (p -> q) & (q -> p)
        assert es_correcto('(p -> q) & (q -> p)', 'p <-> q')

    def test_formula_compleja(self):
        # Distributiva: p & (q | r) ≡ (p & q) | (p & r)
        assert es_correcto('(p & q) | (p & r)', 'p & (q | r)')


# ---------------------------------------------------------------------------
# Casos incorrectos
# ---------------------------------------------------------------------------

class TestIncorrectos:
    def test_conjuncion_vs_disyuncion(self):
        assert not es_correcto('p & q', 'p | q')

    def test_condicional_vs_bicondicional(self):
        assert not es_correcto('p -> q', 'p <-> q')

    def test_condicional_vs_converso(self):
        # p -> q  ≢  q -> p  (no son equivalentes)
        assert not es_correcto('q -> p', 'p -> q')

    def test_negacion_vs_afirmacion(self):
        assert not es_correcto('~p', 'p')

    def test_tautologia_vs_formula_no_tautologica(self):
        assert not es_correcto('p | ~p', 'p -> q')


# ---------------------------------------------------------------------------
# Casos edge del AGENTS.md
# ---------------------------------------------------------------------------

class TestCasosEdge:
    def test_tautologia_vs_tautologia_distintas(self):
        """
        Dos tautologías distintas deben aceptarse como equivalentes.
        Si el docente cargó una tautología, cualquier tautología del
        estudiante se acepta. Comportamiento por diseño (AGENTS.md §5).
        """
        assert es_correcto('p | ~p', 'q | ~q')
        assert es_correcto('p | ~p', '(p -> q) | ~(p -> q)')

    def test_variables_distintas_misma_estructura(self):
        """
        p -> q y a -> b son tabularmente equivalentes (misma función
        booleana, variables renombradas). Aceptado por diseño (AGENTS.md §5).
        """
        assert es_correcto('a -> b', 'p -> q')
        assert es_correcto('a & b', 'p & q')
        assert es_correcto('x | y', 'p | q')

    def test_distintas_variables_distinto_numero_es_incorrecto(self):
        """
        Si la respuesta tiene más variables que la solución, la tabla tiene
        más filas → columnas de resultado de distinto largo → incorrecto.
        """
        # p & q (2 vars, 4 filas) vs p & q & r (3 vars, 8 filas)
        assert not es_correcto('p & q & r', 'p & q')
        assert not es_correcto('p', 'p & q')

    def test_contradiccion_vs_contradiccion(self):
        # Dos contradicciones distintas son equivalentes (ambas siempre False)
        assert es_correcto('p & ~p', 'q & ~q')


class TestArgumentosConRenombramiento:
    def test_tabla_verdad_acepta_misma_forma_con_letras_distintas(self):
        solucion = [
            {'formula': 'P -> (R & D)', 'tipo': 'premisa'},
            {'formula': '~D & R', 'tipo': 'premisa'},
            {'formula': 'P', 'tipo': 'conclusion'},
        ]
        estudiante = [
            {'formula': 'E -> (R & D)', 'tipo': 'premisa'},
            {'formula': '~D & R', 'tipo': 'premisa'},
            {'formula': 'E', 'tipo': 'conclusion'},
        ]
        tabla_estudiante = verificar_argumento(
            estudiante, estudiante, False
        )['tabla_canonica']

        resultado = verificar_argumento(
            estudiante,
            solucion,
            False,
            tabla_estudiante=tabla_estudiante,
        )

        assert resultado['correcto'] is True
        assert resultado['formulas_ok'] is True
        assert resultado['tabla_ok'] is True
        assert resultado['enunciados_ok'] is True
        assert resultado['variables_tabla'] == ['D', 'E', 'R']

    def test_tabla_verdad_rechaza_renombramiento_inconsistente(self):
        solucion = [
            {'formula': 'D -> C', 'tipo': 'premisa'},
            {'formula': 'C -> I', 'tipo': 'premisa'},
            {'formula': 'D -> I', 'tipo': 'conclusion'},
        ]
        estudiante = [
            {'formula': 'E -> S', 'tipo': 'premisa'},
            {'formula': 'E -> D', 'tipo': 'premisa'},
            {'formula': 'E -> D', 'tipo': 'conclusion'},
        ]
        tabla_estudiante = verificar_argumento(
            estudiante, estudiante, True
        )['tabla_canonica']

        resultado = verificar_argumento(
            estudiante,
            solucion,
            True,
            tabla_estudiante=tabla_estudiante,
        )

        assert resultado['correcto'] is False
        assert resultado['formulas_ok'] is False


# ---------------------------------------------------------------------------
# Error de parseo en respuesta del estudiante
# ---------------------------------------------------------------------------

class TestErrorParseo:
    def test_mezcla_and_or_sin_parentesis_devuelve_error_parse(self):
        resultado = verificar('A & B | C', '(A & B) | C')
        assert resultado['correcto'] is False
        assert resultado['error_parse'] is not None
        assert 'Faltan paréntesis' in resultado['error_parse']


    def test_condicional_compuesta_sin_parentesis_devuelve_error_parse(self):
        resultado = verificar('p & q -> r', '(p & q) -> r')
        assert resultado['correcto'] is False
        assert resultado['error_parse'] is not None
        assert 'Faltan paréntesis' in resultado['error_parse']

    def test_condicional_compuesta_con_parentesis_es_valida(self):
        resultado = verificar('(p & q) -> r', '(p & q) -> r')
        assert resultado['correcto'] is True
        assert resultado['error_parse'] is None

    def test_formula_vacia_devuelve_error_parse(self):
        resultado = verificar('', 'p -> q')
        assert resultado['correcto'] is False
        assert resultado['error_parse'] is not None
        assert 'bien formada' in resultado['error_parse']
        assert resultado['tabla_estudiante'] is None
        assert resultado['tabla_solucion'] is None

    def test_caracter_invalido_devuelve_error_parse(self):
        resultado = verificar('p + q', 'p -> q')
        assert resultado['correcto'] is False
        assert resultado['error_parse'] is not None
        assert 'bien formada' in resultado['error_parse']

    def test_parentesis_sin_cerrar_devuelve_error_parse(self):
        resultado = verificar('(p & q', 'p & q')
        assert resultado['correcto'] is False
        assert resultado['error_parse'] is not None
        assert 'bien formada' in resultado['error_parse']

    def test_unicode_no_normalizado_devuelve_error_parse(self):
        # ∧ (wedge) no es el símbolo Copi de conjunción; Copi usa · (punto medio).
        # El motor sugiere '·' en el detalle del mensaje de error.
        resultado = verificar('p \u2227 q', 'p \u00b7 q')
        assert resultado['correcto'] is False
        assert resultado['error_parse'] is not None
        # El mensaje principal debe indicar que no es fbf
        assert 'bien formada' in resultado['error_parse']
        # El detalle técnico (con el símbolo sugerido) debe estar en error_parse_detalle
        assert '\u00b7' in resultado['error_parse_detalle']

    def test_error_parse_no_propaga_excepcion(self):
        # verificar() nunca debe lanzar excepciones por errores del estudiante
        resultado = verificar('&&&&', 'p -> q')
        assert resultado['correcto'] is False
        assert resultado['error_parse'] is not None


# ---------------------------------------------------------------------------
# Estructura del dict de retorno
# ---------------------------------------------------------------------------

class TestEstructuraRetorno:
    def test_claves_presentes_cuando_correcto(self):
        resultado = verificar('p & q', 'p & q')
        assert 'correcto' in resultado
        assert 'error_parse' in resultado
        assert 'tabla_estudiante' in resultado
        assert 'tabla_solucion' in resultado

    def test_claves_presentes_cuando_incorrecto(self):
        resultado = verificar('p | q', 'p & q')
        assert 'correcto' in resultado
        assert 'error_parse' in resultado
        assert 'tabla_estudiante' in resultado
        assert 'tabla_solucion' in resultado

    def test_error_parse_none_cuando_no_hay_error(self):
        resultado = verificar('p -> q', 'p -> q')
        assert resultado['error_parse'] is None
        # error_parse_detalle no está presente cuando no hay error
        assert 'error_parse_detalle' not in resultado

    def test_tablas_none_cuando_hay_error_parse(self):
        resultado = verificar('p >>>>', 'p -> q')
        assert resultado['tabla_estudiante'] is None
        assert resultado['tabla_solucion'] is None

    def test_tablas_tienen_contenido_cuando_correcto(self):
        resultado = verificar('p -> q', 'p -> q')
        assert isinstance(resultado['tabla_estudiante'], list)
        assert isinstance(resultado['tabla_solucion'], list)
        assert len(resultado['tabla_estudiante']) == 4
        assert len(resultado['tabla_solucion']) == 4

    def test_correcto_es_bool(self):
        resultado = verificar('p & q', 'p & q')
        assert isinstance(resultado['correcto'], bool)


# ---------------------------------------------------------------------------
# Bug en fórmula solución → RuntimeError
# ---------------------------------------------------------------------------

class TestErrorSolucion:
    def test_solucion_invalida_lanza_runtime_error(self):
        """
        Si la fórmula solución no parsea, es un bug del sistema (el docente
        cargó una fórmula inválida). verificar() debe lanzar RuntimeError,
        no devolver un resultado silencioso.
        """
        with pytest.raises(RuntimeError, match="solución"):
            verificar('p & q', 'p &&& q')
