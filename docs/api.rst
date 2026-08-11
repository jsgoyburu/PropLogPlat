Referencia de la API
=====================

Documentación completa generada desde los docstrings del código fuente.

motor (interfaz pública)
------------------------

El punto de entrada recomendado para el resto del proyecto Django es el
paquete ``motor`` directamente, que re-exporta las tres funciones públicas:

.. code-block:: python

   from motor import verificar, generar_tabla, parsear

.. automodule:: motor.verificador
   :members: verificar, generar_tabla
   :undoc-members: False
   :show-inheritance:

motor.parser
------------

.. automodule:: motor.parser
   :members: parsear
   :undoc-members: False
   :show-inheritance:

.. note::

   Las clases y funciones privadas del parser (``_Parser``, ``_tokenize``)
   no se documentan aquí porque no forman parte de la interfaz pública.
   Su implementación está comentada en el código fuente.

motor.tabla
-----------

.. automodule:: motor.tabla
   :members: generar_tabla_desde_expr, columna_resultado
   :undoc-members: False
   :show-inheritance:

Índice completo
---------------

* :ref:`genindex`
* :ref:`modindex`
