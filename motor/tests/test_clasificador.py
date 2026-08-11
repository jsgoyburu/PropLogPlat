# motor/tests/test_clasificador.py
"""Tests del clasificador automático de errores de formalización.

Cubre las categorías definidas en motor.clasificador.clasificar_error().
Usa fórmulas concretas en notación Copi (o ASCII normalizado equivalente).
"""

import pytest
from motor.clasificador import clasificar_error
from motor.verificador import distancia_semantica


# ──────────────────────────────────────────────────────────────────────────
#  distancia_semantica
# ──────────────────────────────────────────────────────────────────────────

class TestDistanciaSemantica:
    def test_identicas(self):
        assert distancia_semantica('p -> q', 'p -> q') == 0

    def test_equivalentes_semanticamente(self):
        # ~p | q es equivalente a p -> q
        assert distancia_semantica('~p | q', 'p -> q') == 0

    def test_una_fila_distinta(self):
        # p & q vs p | q: difieren en (T,F) y (F,T) → 2 filas
        assert distancia_semantica('p & q', 'p | q') == 2

    def test_distinto_numero_variables(self):
        assert distancia_semantica('p', 'p & q') is None

    def test_formula_invalida(self):
        assert distancia_semantica('p &&& q', 'p & q') is None

    def test_variables_distintas_mismo_n(self):
        # p -> q vs a -> b: equivalentes bajo renombramiento → distancia 0
        assert distancia_semantica('p -> q', 'a -> b') == 0

    def test_polaridad(self):
        # p & q vs ~(p & q): todas filas invertidas → distancia == n_filas
        d = distancia_semantica('p & q', '~(p & q)')
        assert d == 4  # 2 variables → 4 filas, todas invertidas

    def test_sin_variables(self):
        # Fórmulas tautológicas (sin vars libres en sympy a veces)
        # p | ~p vs q | ~q: ambas siempre True
        # Solo cuando sympy simplifica completamente; en el motor no suele ocurrir
        # así que testeamos el caso normal de comparar tautologías con variables
        d = distancia_semantica('p | ~p', 'p | ~p')
        assert d == 0


# ──────────────────────────────────────────────────────────────────────────
#  clasificar_error: tautología y contradicción
# ──────────────────────────────────────────────────────────────────────────

class TestTautologiaContraddiccion:
    def test_tautologia(self):
        # p | ~p es tautología
        assert clasificar_error('p | ~p', 'p -> q') == 'tautologia'

    def test_tautologia_compuesta(self):
        assert clasificar_error('(p -> q) | ~(p -> q)', 'p & q') == 'tautologia'

    def test_contradiccion(self):
        # p & ~p es contradicción
        assert clasificar_error('p & ~p', 'p -> q') == 'contradiccion'

    def test_contradiccion_compuesta(self):
        assert clasificar_error('(p & q) & ~(p & q)', 'p | q') == 'contradiccion'


# ──────────────────────────────────────────────────────────────────────────
#  clasificar_error: polaridad
# ──────────────────────────────────────────────────────────────────────────

class TestPolaridad:
    def test_polaridad_simple(self):
        # Solución: p & q  →  negación exacta: ~(p & q)  →  ~p | ~q
        # La tabla de ~(p & q) es exactamente la inversa de p & q
        assert clasificar_error('~p | ~q', 'p & q') == 'polaridad'

    def test_polaridad_condicional(self):
        # Solución p -> q; negación: ~(p -> q) = p & ~q
        assert clasificar_error('p & ~q', 'p -> q') == 'polaridad'


# ──────────────────────────────────────────────────────────────────────────
#  clasificar_error: variables extra/menos
# ──────────────────────────────────────────────────────────────────────────

class TestVariables:
    def test_variables_extra(self):
        # Solución con 1 variable, estudiante usa 2
        assert clasificar_error('p & q', 'p') == 'variables_extra'

    def test_variables_extra_tres(self):
        assert clasificar_error('p & q & r', 'p & q') == 'variables_extra'

    def test_variables_menos(self):
        # Solución con 2 variables, estudiante usa 1
        assert clasificar_error('p', 'p & q') == 'variables_menos'

    def test_variables_menos_tres_vs_dos(self):
        assert clasificar_error('p', 'p & q & r') == 'variables_menos'


# ──────────────────────────────────────────────────────────────────────────
#  clasificar_error: mas_fuerte / mas_debil
# ──────────────────────────────────────────────────────────────────────────

class TestFuertDebil:
    def test_mas_fuerte(self):
        # Solución: p | q (3 True de 4)
        # Estudiante: p & q (1 True de 4): todo True del estudiante → True en solución
        # Sol ⊨ est: no (cuando sol=True, est puede ser False)
        # Est ⊨ sol: sí (cuando est=True, sol=True)
        # Entonces est ⊨ sol pero no sol ⊨ est → 'mas_debil' (perdió condición)
        # ... espera, según spec: mas_fuerte = sol ⊨ est pero no al revés
        # Sol (p|q) ⊨ est (p&q)? → NO (p=T,q=F: sol=T, est=F)
        # Est (p&q) ⊨ sol (p|q)? → SÍ (p=T,q=T: est=T, sol=T; otros: est=F)
        # → est ⊨ sol AND NOT sol ⊨ est → mas_debil (el estudiante perdió condición)
        assert clasificar_error('p & q', 'p | q') == 'mas_debil'

    def test_mas_debil(self):
        # Solución: p & q (1 True de 4)
        # Estudiante: p | q (3 True de 4)
        # Sol ⊨ est? (cuando sol=True: p=T,q=T → est=T) SÍ
        # Est ⊨ sol? (cuando est=True: p=T,q=F → sol=F) NO
        # → sol ⊨ est AND NOT est ⊨ sol → mas_fuerte
        assert clasificar_error('p | q', 'p & q') == 'mas_fuerte'

    def test_mas_debil_condicional(self):
        # Solución: p -> q (equivale a ~p | q, 3 True de 4)
        # Estudiante: p & q (1 True de 4)
        # est ⊨ sol: cuando p&q=T (solo p=T,q=T) → p->q=T → SÍ
        # sol ⊨ est: cuando p->q=T (T,T), (F,T), (F,F) → est=F en (F,T) → NO
        assert clasificar_error('p & q', 'p -> q') == 'mas_debil'


# ──────────────────────────────────────────────────────────────────────────
#  clasificar_error: errores parciales
# ──────────────────────────────────────────────────────────────────────────

class TestErroresParciales:
    def test_error_parcial_1(self):
        # p -> q tiene 4 filas. Necesitamos una fórmula que difiera en exactamente 1.
        # p -> q: T,F,T,T (para TT,TF,FT,FF con vars p,q ordenados)
        # Buscar algo que difiera en 1 sola fila.
        # q -> p: T,T,F,T → difiere en fila 2 (TF: q->p=T, p->q=F) y fila 3 (FT: q->p=F, p->q=T)
        # Eso son 2 filas. Busquemos otra fórmula.
        # p <-> q: T,F,F,T → difiere en fila 3 (FT: bicondicional=F, p->q=T)...
        # p->q: (T,T)=T, (T,F)=F, (F,T)=T, (F,F)=T
        # p<->q: (T,T)=T, (T,F)=F, (F,T)=F, (F,F)=T → difiere en fila 3 → distancia 1!
        assert clasificar_error('p <-> q', 'p -> q') == 'error_parcial_1'

    def test_error_parcial_2(self):
        # p -> q vs q -> p: difieren en 2 filas
        # p->q: T,F,T,T (para TT,TF,FT,FF)
        # q->p: T,T,F,T (para TT,TF,FT,FF)
        # Fila TF: p->q=F, q->p=T → diferente
        # Fila FT: p->q=T, q->p=F → diferente
        # → distancia 2
        assert clasificar_error('q -> p', 'p -> q') == 'error_parcial_2'


# ──────────────────────────────────────────────────────────────────────────
#  clasificar_error: sin_clasificar y equivalente_alt
# ──────────────────────────────────────────────────────────────────────────

class TestCasosEspeciales:
    def test_formula_invalida_estudiante(self):
        # Fórmula que no puede parsearse → sin_clasificar
        assert clasificar_error('p &&& q', 'p & q') == 'sin_clasificar'

    def test_equivalente_alt_variables_distintas(self):
        # Misma estructura con variables distintas: el motor puede haber rechazado
        # por diccionario incorrecto, pero semánticamente es equivalente.
        # a -> b es equivalente a p -> q bajo renombramiento a=p, b=q
        # Si distancia mínima = 0 → equivalente_alt
        resultado = clasificar_error('a -> b', 'p -> q')
        # Con el mismo número de variables, prueba permutaciones
        # a->b bajo (a=p, b=q) → p->q = p->q → distancia 0 → equivalente_alt
        assert resultado == 'equivalente_alt'


# ──────────────────────────────────────────────────────────────────────────
#  clasificar_error: error sistémico
# ──────────────────────────────────────────────────────────────────────────

class TestErrorSistemico:
    def test_error_sistemico_tres_variables(self):
        # Con 3 variables: 8 filas. Sistémico si distancia > 4.
        # p -> (q -> r): tabla con muchos True
        # ~p & ~q & ~r: solo 1 True (FFF) → distancia contra p->(q->r) que es
        # False solo en (T,T,F) → True en 7/8 filas
        # ~p & ~q & ~r: True solo en (F,F,F) → True en 1/8
        # Coincidencia solo en (F,F,F) que en p->(q->r) también es True
        # Resto: est=F, sol=T → 7 discordancias (7 > 4) → sistémico
        resultado = clasificar_error('~p & ~q & ~r', 'p -> (q -> r)')
        assert resultado == 'error_sistemico'
