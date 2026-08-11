Referencia de la plataforma
============================

Esta sección describe las apps Django y los flujos funcionales de la plataforma.
Para la arquitectura técnica completa, ver ``ARCHITECTURE.md`` en la raíz del repositorio.

Apps Django
-----------

accounts
~~~~~~~~

Usuarios, onboarding y consentimientos informados.

**Modelos principales:**

- ``Usuario``: extiende ``AbstractUser``. Campos: ``es_docente``, ``debe_cambiar_password``, ``consentimiento_pedagogico``, ``consentimiento_investigacion``, ``consentimiento_contacto_seguimiento``, ``encuesta_completada``.
- ``ConfigSitio``: singleton global. Porta nombre del sitio, colores, favicon (base64), y umbrales analíticos configurables.
- ``EncuestaEstudiante``: survey socioeducativo (OneToOne → Usuario). Solo se crea si ``consentimiento_pedagogico=True``.

**Middleware:**

``ForzarCambioPasswordMiddleware`` intercepta todas las requests post-login. Redirige al flujo de onboarding si: (1) debe cambiar contraseña, (2) algún consentimiento es ``None``, (3) es estudiante con consentimiento pedagógico y encuesta incompleta.

**Acceso por link de comisión:**

La URL ``/accounts/comision/<pk>/acceso/`` permite a estudiantes registrarse y quedar inscriptos automáticamente en esa comisión.

cursos
~~~~~~

Comisiones e inscripciones.

- ``Comision``: unidad pedagógica (clase). N docentes, M estudiantes (through ``Inscripcion``). Campo ``tipo_encuesta``: ``'completa'`` o ``'basica'``.
- ``Inscripcion``: through-table explícito. Permite enriquecer la relación en el futuro.

ejercicios
~~~~~~~~~~

Núcleo académico del sistema.

**Modelos:**

- ``Ejercicio``: enunciado + solución + tipo (``formalizacion`` / ``tabla_verdad`` / ``determinacion_verdad``).
- ``Practica``: entidad canónica. Agrupa ejercicios ordenados. Puede tener ``practica_origen`` (FK self) si es importada.
- ``PracticaComision``: asignación de práctica a comisión con orden y fechas opcionales.
- ``EjercicioPractica``: through-table con campo ``orden``. Determina la secuencia de desbloqueo.
- ``Intento``: registro de cada intento de resolución. Campos: ``es_correcto`` (motor), ``aprobado_docente`` (docente), ``comentario_docente``.
- ``Progreso``: apuntador al ejercicio actual por estudiante en cada práctica.

**Tipos de ejercicio:**

.. list-table::
   :header-rows: 1

   * - Tipo
     - Descripción
   * - ``formalizacion``
     - Traducir un enunciado en lenguaje natural a fórmula proposicional
   * - ``tabla_verdad``
     - Construir la tabla de verdad completa de una fórmula
   * - ``determinacion_verdad``
     - Determinar el valor de verdad de una fórmula para una asignación dada

docentes
~~~~~~~~

Panel docente. Interfaz propia, optimizada para uso no técnico (no admin-first).

**Vistas principales:**

- ``comisiones_list``: dashboard del docente con banco de prácticas.
- ``comision_detail``: estudiantes, prácticas asignadas, analíticas (cacheadas 5 min).
- ``ejercicio_form``: CRUD de ejercicios con sandbox de verificación en tiempo real.
- ``practica_form``: CRUD de prácticas con CKEditor5.
- ``practica_detail``: gestión de ejercicios dentro de una práctica.
- ``estudiante_detail``: perfil del estudiante con historial de intentos.
- ``correccion_pendiente``: cola paginada (25/página) de intentos sin revisión docente.

**Copy-on-write:**

Al importar una práctica del banco, ``practica_origen`` se setea. Si el docente edita la copia, ``_desanclar_si_derivada()`` limpia ``practica_origen`` y la práctica vuelve a ser independiente. El banco solo muestra ``practica_origen IS NULL``.

analiticas
~~~~~~~~~~

Métricas pedagógicas. Herramienta de intervención, no de ranking.

**Métricas disponibles:**

.. list-table::
   :header-rows: 1

   * - Métrica
     - Descripción
   * - Ejercicios más difíciles
     - Top N por tasa de error
   * - Distribución de intentos
     - Histograma de intentos hasta resolver (por ejercicio, desplegable por comisión)
   * - Señales de alerta
     - Estudiantes con N fallos consecutivos sin éxito
   * - Errores sistemáticos
     - Respuestas incorrectas compartidas por múltiples estudiantes
   * - Evolución temporal
     - Intentos por semana (ventana 8 semanas)
   * - Silencio
     - Estudiantes sin actividad hace N días
   * - Arranque tardío
     - Estudiantes sin intentos en los primeros N días

Los umbrales son configurables en ``ConfigSitio`` y visibles en pantalla.

API REST
--------

``POST /api/intentos/``
~~~~~~~~~~~~~~~~~~~~~~~

Crea un intento de resolución. Llama al motor, actualiza el progreso, retorna el resultado.

**Request:**

.. code-block:: json

   {
     "ejercicio_practica": 42,
     "practica_comision": 7,
     "respuesta_raw": "~p | q",
     "diccionario": {"p": "Llueve", "q": "Hay tráfico"}
   }

**Response (correcto):**

.. code-block:: json

   {
     "correcto": true,
     "error_parse": null,
     "tabla_estudiante": null,
     "tabla_solucion": null
   }

**Response (incorrecto):**

.. code-block:: json

   {
     "correcto": false,
     "error_parse": null,
     "tabla_estudiante": [{"p": true, "q": true, "resultado": false}],
     "tabla_solucion": [{"p": true, "q": true, "resultado": true}]
   }

**Errores:**

- ``403``: estudiante no inscripto en la comisión, o práctica no disponible.
- ``400``: datos de request inválidos.
- ``500``: fórmula solución del ejercicio no pudo parsearse (bug del sistema).

Comandos de gestión
-------------------

``reevaluar_tablas_verdad``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Revalida intentos históricos de ejercicios de tabla de verdad con el motor actual.
Preserva ``aprobado_docente`` y no retrocede a estudiantes que ya avanzaron.

.. code-block:: bash

   python manage.py reevaluar_tablas_verdad --dry-run
   python manage.py reevaluar_tablas_verdad

``reconciliar_disyuncion_v``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Reconcilia intentos afectados por el bug del parser de ``v`` minúscula como disyunción
(``JvM`` no era reconocido). Si un intento cambia a correcto y estaba ``aprobado_docente=False``,
lo pasa a ``None`` (pendiente de revisión docente).

.. code-block:: bash

   python manage.py reconciliar_disyuncion_v --dry-run
   python manage.py reconciliar_disyuncion_v
