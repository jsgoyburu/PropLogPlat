Cómo funciona la verificación
==============================

El motor verifica respuestas de estudiantes comparando **tablas de verdad**,
no formas sintácticas. Esta sección explica la mecánica, las limitaciones
conocidas, y las decisiones de diseño.

Flujo de una corrección
-----------------------

.. code-block:: text

   Estudiante ingresa fórmula
         ↓
   Frontend normaliza a ASCII
   (⊃→->, ∧→&, ¬→~, ↔→<->; y también se acepta . como conjunción)
         ↓
   POST /api/intentos/ {ejercicio_id, respuesta_raw}
         ↓
   View llama motor.verificar(respuesta_raw, formula_solucion)
         ↓
   motor.verificar():
     1. Parsear respuesta del estudiante
     2. Parsear fórmula solución (cargada por docente)
     3. Generar tabla de verdad de cada fórmula
     4. Comparar columnas de resultado
         ↓
   Retorna {correcto, error_parse, tabla_estudiante, tabla_solucion}
         ↓
   View actualiza progreso (si correcto) y devuelve feedback
         ↓
   Frontend muestra tablas lado a lado (si incorrecto)
   o confirmación (si correcto)

Equivalencia tabular
---------------------

La corrección se basa en **equivalencia semántica**: dos fórmulas son
equivalentes si y sólo si tienen la misma columna de resultado en su tabla
de verdad.

Formalmente: *A* ≡ *B* si y sólo si para toda valuación *v*,
*v*(*A*) = *v*(*B*).

Esto permite que el estudiante ingrese cualquier fórmula semánticamente
equivalente a la solución, sin importar la forma sintáctica. Por ejemplo,
si la solución es ``p -> q``, el motor acepta como correctas:

- ``p -> q``  (idéntica)
- ``~p | q``  (equivalencia del condicional)
- ``~(p & ~q)``  (De Morgan)
- ``~~(~p | q)``  (doble negación)

Limitaciones conocidas y aceptadas
------------------------------------

Estas limitaciones son consecuencia del diseño por equivalencia tabular y
están documentadas en AGENTS.md §5.

Variables distintas
~~~~~~~~~~~~~~~~~~~

El motor no puede verificar que el estudiante usó las mismas variables que
la solución. Sólo compara las columnas de resultado.

Consecuencia: ``p -> q`` y ``a -> b`` son aceptadas como equivalentes porque
tienen el mismo número de variables (2) y la misma tabla de verdad cuando se
ordenan sus variables alfabéticamente.

Esto es una **limitación pedagógica conocida y aceptada**: no se puede
detectar si el estudiante formalizó correctamente las variables de la
consigna.

.. note::

   Para ejercicios donde la elección de variables es parte del aprendizaje
   (p.ej., "formalizá 'si llueve entonces me mojo' usando *p* para 'llueve'
   y *q* para 'me mojo'"), el docente debe complementar la corrección
   automática con revisión manual.

Tautología vs. tautología
~~~~~~~~~~~~~~~~~~~~~~~~~~

Si el docente carga una tautología como solución, **cualquier tautología** del
estudiante es aceptada, independientemente del número de variables.

Por ejemplo, si la solución es ``p | ~p``, el motor acepta:

- ``q | ~q``
- ``(p -> q) | ~(p -> q)``
- ``(r & s) | ~(r & s)``

**El docente debe ser consciente de esto al cargar ejercicios.** Si la
intención es que el estudiante demuestre que *una fórmula específica* es
tautológica, el ejercicio debe formularse de modo que la solución no sea
una tautología genérica.

Contradicción vs. contradicción
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ídem para contradicciones: si la solución es ``p & ~p``, cualquier
contradicción es aceptada.

No detecta variables extra
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Si el estudiante agrega variables que no aparecen en la solución, la tabla
de verdad tiene más filas (más variables → más combinaciones), y la
comparación falla automáticamente por longitud distinta.

Por ejemplo, si la solución es ``p & q`` (4 filas) y el estudiante escribe
``p & q & r`` (8 filas), la respuesta se marca como incorrecta.

Estructura del retorno
-----------------------

:func:`motor.verificador.verificar` devuelve siempre un ``dict`` con
cuatro claves:

.. code-block:: python

   {
       "correcto": bool,
       "error_parse": str | None,
       "tabla_estudiante": list[dict] | None,
       "tabla_solucion": list[dict] | None,
   }

Cuando ``error_parse`` no es ``None``, las tablas son ``None`` y ``correcto``
es ``False``.

Ejemplo de uso en una view Django::

   from motor import verificar
   from .models import Intento, Progreso

   def crear_intento(request, ejercicio_practica_id):
       ep = get_object_or_404(EjercicioPractica, pk=ejercicio_practica_id)
       respuesta_raw = request.POST.get('respuesta', '').strip()

       try:
           resultado = verificar(respuesta_raw, ep.ejercicio.formula_solucion)
       except RuntimeError as e:
           # Bug en la solución del docente — loguear y devolver 500
           logger.error("Fórmula solución inválida en ejercicio %s: %s",
                        ep.ejercicio.pk, e)
           return JsonResponse({'error': 'Error interno'}, status=500)

       Intento.objects.create(
           estudiante=request.user,
           ejercicio_practica=ep,
           respuesta_raw=respuesta_raw,
           es_correcto=resultado['correcto'],
       )

       if resultado['correcto']:
           _avanzar_progreso(request.user, ep)

       return JsonResponse(resultado)

Manejo de errores
-----------------

El motor distingue tres categorías de error:

**Error del estudiante (ValueError → error_parse)**
   La fórmula del estudiante no pudo parsearse. La función retorna con
   ``correcto=False`` y el mensaje de error en ``error_parse``. Nunca
   lanza excepción.

**Bug del sistema (RuntimeError)**
   La fórmula solución del ejercicio no pudo parsearse. Esto indica un
   problema en la carga del ejercicio, no un error del estudiante. La
   view debe capturar este error, loguearlo como error del sistema, y
   devolver HTTP 500. **No mostrar el mensaje de RuntimeError al estudiante.**

**Excepción no esperada**
   Cualquier otra excepción es un bug del motor. Debe loguearse y no
   llegar al estudiante.
