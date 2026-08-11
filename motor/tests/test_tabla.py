# motor/tests/test_tabla.py
"""
Tests para motor.tabla (via motor.verificador.generar_tabla)

Cubre:
  - Estructura correcta del dict de cada fila
  - Orden de filas (estándar: de todo-True a todo-False)
  - Número de filas: 2^n para n variables
  - Tablas conocidas para cada conectivo
  - Tautología y contradicción
  - Fórmula con una sola variable
  - Fórmula con tres variables
"""

import pytest
from motor.verificador import generar_tabla


# ---------------------------------------------------------------------------
# Estructura y orden
# ---------------------------------------------------------------------------

class TestEstructura:
    def test_claves_incluyen_variables_y_resultado(self):
        tabla = generar_tabla('p & q')
        assert 'p' in tabla[0]
        assert 'q' in tabla[0]
        assert 'resultado' in tabla[0]

    def test_valores_son_booleanos(self):
        tabla = generar_tabla('p -> q')
        for fila in tabla:
            for clave, valor in fila.items():
                assert isinstance(valor, bool), (
                    f"El valor de '{clave}' no es bool: {type(valor)}"
                )

    def test_numero_de_filas_una_variable(self):
        tabla = generar_tabla('~p')
        assert len(tabla) == 2       # 2^1

    def test_numero_de_filas_dos_variables(self):
        tabla = generar_tabla('p & q')
        assert len(tabla) == 4       # 2^2

    def test_numero_de_filas_tres_variables(self):
        tabla = generar_tabla('p & q & r')
        assert len(tabla) == 8       # 2^3

    def test_orden_filas_dos_variables(self):
        # Orden esperado: TT, TF, FT, FF (alfabético por nombre de var)
        tabla = generar_tabla('p | q')
        assert tabla[0]['p'] is True  and tabla[0]['q'] is True
        assert tabla[1]['p'] is True  and tabla[1]['q'] is False
        assert tabla[2]['p'] is False and tabla[2]['q'] is True
        assert tabla[3]['p'] is False and tabla[3]['q'] is False

    def test_variables_ordenadas_alfabeticamente(self):
        # 'r' antes que 'z'; las dos primeras columnas deben ser r y z
        tabla = generar_tabla('z | r')
        # Primera columna en orden alfabético: r, z
        assert 'r' in tabla[0] and 'z' in tabla[0]
        # Primera fila: r=T, z=T (r antes que z)
        assert tabla[0]['r'] is True
        assert tabla[0]['z'] is True


# ---------------------------------------------------------------------------
# Tablas de verdad conocidas
# ---------------------------------------------------------------------------

class TestNegacion:
    def test_negacion(self):
        tabla = generar_tabla('~p')
        # Orden: p=T → resultado=F; p=F → resultado=T
        assert tabla[0] == {'p': True,  'resultado': False}
        assert tabla[1] == {'p': False, 'resultado': True}


class TestConjuncion:
    def test_conjuncion(self):
        tabla = generar_tabla('p & q')
        esperada = [
            {'p': True,  'q': True,  'resultado': True},
            {'p': True,  'q': False, 'resultado': False},
            {'p': False, 'q': True,  'resultado': False},
            {'p': False, 'q': False, 'resultado': False},
        ]
        assert tabla == esperada


class TestDisyuncion:
    def test_disyuncion(self):
        tabla = generar_tabla('p | q')
        esperada = [
            {'p': True,  'q': True,  'resultado': True},
            {'p': True,  'q': False, 'resultado': True},
            {'p': False, 'q': True,  'resultado': True},
            {'p': False, 'q': False, 'resultado': False},
        ]
        assert tabla == esperada


class TestCondicional:
    def test_condicional(self):
        tabla = generar_tabla('p -> q')
        esperada = [
            {'p': True,  'q': True,  'resultado': True},
            {'p': True,  'q': False, 'resultado': False},
            {'p': False, 'q': True,  'resultado': True},
            {'p': False, 'q': False, 'resultado': True},
        ]
        assert tabla == esperada


class TestBicondicional:
    def test_bicondicional(self):
        tabla = generar_tabla('p <-> q')
        esperada = [
            {'p': True,  'q': True,  'resultado': True},
            {'p': True,  'q': False, 'resultado': False},
            {'p': False, 'q': True,  'resultado': False},
            {'p': False, 'q': False, 'resultado': True},
        ]
        assert tabla == esperada


# ---------------------------------------------------------------------------
# Casos especiales
# ---------------------------------------------------------------------------

class TestTautologiaYContradiccion:
    def test_tautologia_simple(self):
        tabla = generar_tabla('p | ~p')
        assert all(fila['resultado'] is True for fila in tabla)

    def test_contradiccion_simple(self):
        tabla = generar_tabla('p & ~p')
        assert all(fila['resultado'] is False for fila in tabla)

    def test_tautologia_dos_variables(self):
        # p -> p es tautología
        tabla = generar_tabla('p -> p')
        assert all(fila['resultado'] is True for fila in tabla)

    def test_tautologia_compleja(self):
        # Modus ponens como tautología: (p & (p -> q)) -> q
        tabla = generar_tabla('(p & (p -> q)) -> q')
        assert all(fila['resultado'] is True for fila in tabla)


class TestFormulasEquivalentes:
    def test_condicional_equivale_a_disyuncion(self):
        # p -> q  ≡  ~p | q
        tabla1 = generar_tabla('p -> q')
        tabla2 = generar_tabla('~p | q')
        res1 = [f['resultado'] for f in tabla1]
        res2 = [f['resultado'] for f in tabla2]
        assert res1 == res2

    def test_demorgan_and(self):
        # ~(p & q) ≡ ~p | ~q
        tabla1 = generar_tabla('~(p & q)')
        tabla2 = generar_tabla('~p | ~q')
        res1 = [f['resultado'] for f in tabla1]
        res2 = [f['resultado'] for f in tabla2]
        assert res1 == res2

    def test_demorgan_or(self):
        # ~(p | q) ≡ ~p & ~q
        tabla1 = generar_tabla('~(p | q)')
        tabla2 = generar_tabla('~p & ~q')
        res1 = [f['resultado'] for f in tabla1]
        res2 = [f['resultado'] for f in tabla2]
        assert res1 == res2


class TestTresVariables:
    def test_dimension_correcta(self):
        tabla = generar_tabla('(p -> q) & (q -> r)')
        assert len(tabla) == 8
        # Todas las filas deben tener p, q, r, resultado
        for fila in tabla:
            assert set(fila.keys()) == {'p', 'q', 'r', 'resultado'}

    def test_silogismo_hipotetico(self):
        # (p -> q) & (q -> r) -> (p -> r) es tautología
        tabla = generar_tabla('((p -> q) & (q -> r)) -> (p -> r)')
        assert all(fila['resultado'] is True for fila in tabla)


class TestErrores:
    def test_formula_invalida_lanza_error(self):
        with pytest.raises(ValueError):
            generar_tabla('p &&& q')

    def test_formula_vacia_lanza_error(self):
        with pytest.raises(ValueError):
            generar_tabla('')
