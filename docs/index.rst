PropLogPlat — Documentación técnica
====================================

Plataforma web para práctica de **lógica proposicional** en IPC/CBC-UBA.
Diseñada como apoyo pedagógico para el trabajo docente en cursos masivos.

La plataforma implementa una **arquitectura híbrida humano–máquina**:

- **La máquina** realiza verificación formal, registra intentos y visibiliza procesos.
- **El/la docente** interpreta errores, acompaña trayectorias y toma decisiones de evaluación.

.. note::

   Esta documentación cubre la API técnica y el motor lógico.
   Para el marco pedagógico completo, ver ``WHITE_PAPER.md`` en la raíz del repositorio.
   Para la arquitectura técnica exhaustiva, ver ``ARCHITECTURE.md``.

.. toctree::
   :maxdepth: 2
   :caption: Motor lógico

   sintaxis
   verificacion
   api

.. toctree::
   :maxdepth: 1
   :caption: Referencia rápida

   plataforma

----

Inicio rápido — Motor lógico
------------------------------

Instalar dependencias::

   pip install sympy

Usar el motor::

   from motor import verificar, generar_tabla, parsear

   # Generar tabla de verdad
   tabla = generar_tabla('p -> q')
   # → [{'p': True, 'q': True, 'resultado': True}, ...]

   # Verificar respuesta de un estudiante
   resultado = verificar('~p | q', 'p -> q')
   resultado['correcto']   # → True  (equivalentes semánticamente)

   # Solo parsear
   expr = parsear('p & (q | ~r)')
   # → And(p, Or(q, Not(r)))  [expresión sympy]

Correr los tests del motor::

   pytest motor/tests/

----

Módulos del motor
-----------------

El motor está compuesto por tres módulos (sin dependencias de Django):

:mod:`motor.parser`
   Tokenizador y parser de descenso recursivo. Convierte una cadena
   en notación Copi o ASCII en una expresión :mod:`sympy`.

:mod:`motor.tabla`
   Generación de tablas de verdad a partir de expresiones sympy.

:mod:`motor.verificador`
   Interfaz pública. El resto del proyecto Django sólo necesita importar
   desde aquí: ``from motor import verificar, generar_tabla, parsear``.

----

Stack técnico
-------------

- **Backend:** Django 5 + Django REST Framework
- **Base de datos:** SQLite (local) / PostgreSQL (Railway)
- **Motor lógico:** SymPy (``sympy.logic``)
- **Frontend:** Templates Django + Alpine.js
- **Rich text:** django-ckeditor-5
- **Deploy:** Railway + Gunicorn + WhiteNoise

----

Importación masiva de estudiantes
-----------------------------------

El panel docente permite importar estudiantes en lote desde archivos Excel.
El archivo debe incluir columnas en este orden: ``username``, ``email``,
``password``. Cada fila se valida de forma independiente; si una fila falla,
se omite y la importación continúa con las demás.

----

Decisiones de diseño
----------------------

El motor es una **librería Python pura** sin modelos ni views. Esto permite
testearlo de forma aislada y reemplazarlo sin tocar el stack web.
Ver ``AGENTS.md`` §6 para la tabla completa de decisiones de diseño.

La corrección es **semántica** (tablas de verdad), no sintáctica. Las
limitaciones conocidas están documentadas en :func:`motor.verificador.verificar`
y en :doc:`verificacion`.
