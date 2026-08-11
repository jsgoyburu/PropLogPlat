Sintaxis de fórmulas
====================

El motor acepta fórmulas proposicionales en **notación Copi** (Irving Copi,
*Introduction to Logic*), que es la notación usada en los cursos IPC/CBC-UBA.
Se aceptan también alternativas ASCII equivalentes para facilitar la entrada
por teclado estándar.

Conectivos
----------

La notación primaria es Copi. La columna "ASCII alt" muestra el equivalente
aceptado como alternativa.

.. list-table::
   :header-rows: 1
   :widths: 15 15 30 40

   * - Copi
     - ASCII alt
     - Conectivo
     - Ejemplo
   * - ``~``
     - ``~``
     - Negación
     - ``~p``
   * - ``·``
     - ``&``, ``.``
     - Conjunción
     - ``p · q``
   * - ``∨``
     - ``|``
     - Disyunción
     - ``p ∨ q``
   * - ``⊃``
     - ``->``
     - Condicional
     - ``p ⊃ q``
   * - ``≡``
     - ``<->``
     - Bicondicional
     - ``p ≡ q``

.. note::

   El motor acepta indistintamente los símbolos Copi y sus equivalentes ASCII.
   Se puede escribir ``p ⊃ (q · r)``, ``p -> (q & r)`` o ``p -> (q . r)`` y mezclarlos.
   El frontend on-screen keyboard inserta Copi; el usuario también puede
   escribir ``->`` para el condicional.

Variantes no soportadas
~~~~~~~~~~~~~~~~~~~~~~~~

Los siguientes símbolos **no** son aceptados por el motor (el tokenizador
lanza :exc:`ValueError` con sugerencia del equivalente Copi):

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Símbolo no soportado
     - Sugerencia
   * - ``∧`` (U+2227 LOGICAL AND)
     - Usar ``·`` (punto medio, U+00B7) — conjunción Copi
   * - ``→`` (U+2192 RIGHTWARDS ARROW)
     - Usar ``⊃`` o ``->``
   * - ``↔`` (U+2194 LEFT RIGHT ARROW)
     - Usar ``≡`` o ``<->``
   * - ``¬`` (U+00AC NOT SIGN)
     - Usar ``~``

Variables
---------

Las variables son identificadores que comienzan con una letra y pueden
contener letras, dígitos y guiones bajos:

- Válidas: ``p``, ``q``, ``r``, ``p1``, ``q2``, ``P``, ``prem``
- Inválidas: ``1p`` (empieza con dígito), ``p-q`` (guión no permitido)

Las mayúsculas y minúsculas se distinguen: ``P`` y ``p`` son variables
distintas.

Agrupación
----------

Los paréntesis ``()`` se usan para agrupación explícita y anulan la
precedencia predeterminada:

- ``~p · q``  →  ``(~p) · q``   (por precedencia: ~ liga más que ·)
- ``~(p · q)`` →  negación de la conjunción completa

Precedencia
-----------

De mayor a menor binding (mayor binding significa que liga más fuerte):

.. list-table::
   :header-rows: 1
   :widths: 10 15 75

   * - Nivel
     - Operador (Copi)
     - Nota
   * - 1 (mayor)
     - ``~``
     - Prefijo, right-associative. ``~~p`` = ``Not(Not(p))``
   * - 2
     - ``·``
     - Left-associative. ``p · q · r`` = ``(p · q) · r``
   * - 3
     - ``∨``
     - Left-associative.
   * - 4
     - ``⊃``
     - **Right-associative.** ``p ⊃ q ⊃ r`` = ``p ⊃ (q ⊃ r)``
   * - 5 (menor)
     - ``≡``
     - Left-associative.

.. admonition:: Por qué el condicional es right-associative

   En lógica clásica, ``p ⊃ (q ⊃ r)`` y ``(p ⊃ q) ⊃ r`` tienen tablas de
   verdad distintas. La convención right-associative para ``⊃`` es la
   estándar en lógica proposicional y coincide con la notación usada en
   IPC/CBC-UBA. Si se necesita la interpretación left-associativa, se debe
   usar paréntesis explícitos: ``(p ⊃ q) ⊃ r``.

Ejemplos de fórmulas válidas
-----------------------------

Fórmulas atómicas::

   p
   q1
   P

Fórmulas compuestas (notación Copi)::

   ~p
   p · q
   p ∨ q ∨ r
   p ⊃ q
   p ≡ q
   ~p ∨ q           # equivale a p ⊃ q
   p · (q ∨ r)      # distribución
   (p ⊃ q) · (q ⊃ r) ⊃ (p ⊃ r)   # silogismo hipotético
   ((p ⊃ q) · ~q) ⊃ ~p             # modus tollens

Las mismas fórmulas con alternativas ASCII::

   ~p ∨ q           # Copi
   ~p | q           # ASCII equiv
   p . q            # ASCII equiv (conjunción)
   p ⊃ q            # Copi
   p -> q           # ASCII equiv

Errores comunes
---------------

El motor lanza :exc:`ValueError` con mensajes descriptivos para los siguientes
casos:

**Fórmula vacía**::

   parsear('')
   # ValueError: La fórmula está vacía.

**Símbolo no soportado** (∧ no es el símbolo Copi de conjunción)::

   parsear('p ∧ q')
   # ValueError: Carácter no reconocido: '∧' — Usar '·' para la conjunción (notación Copi).

**Conectivo sin operando**::

   parsear('p ·')
   # ValueError: Se esperaba una variable o '(', pero se encontró 'fin de fórmula'.

**Paréntesis sin cerrar**::

   parsear('(p · q')
   # ValueError: Paréntesis de cierre ')' faltante.

**Token inesperado al final**::

   parsear('p q')
   # ValueError: Token inesperado 'q' al final de la fórmula.
