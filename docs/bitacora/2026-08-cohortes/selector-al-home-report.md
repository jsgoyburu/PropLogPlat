# Selector de cohorte al home del panel docente

Rama `claude/desbloqueo-configurable`, sobre `a34948c`.

## Resumen de los tres cambios

1. El botón "Nueva cohorte" se movió de `comision_detail.html` a `comisiones_list.html` (home del panel).
2. El selector de cohorte se movió al home y la selección pasó a ser global, persistida en sesión, con querystring `?cohorte=` como override.
3. `correccion_pendiente` ganó un filtro de cohorte que defaultea a la activa, con "Todas las camadas" como opción explícita y siempre visible.

## Archivos tocados

- `docentes/views.py` — toda la lógica de resolución de cohorte, `comisiones_list`, `comision_detail` y las vistas que resuelven cohorte, `cohorte_create`, `correccion_pendiente`.
- `templates/docentes/_selector_cohorte.html` — reducido a badge + aviso de "cohorte cerrada" (ya no tiene el `<select>` ni el botón de crear).
- `templates/docentes/_selector_cohorte_home.html` — **nuevo**: el `<select>` de cohorte + botón "Nueva cohorte", incluido desde `comisiones_list.html`.
- `templates/docentes/comisiones_list.html` — incluye el nuevo selector.
- `templates/docentes/correccion_pendiente.html` — nuevo `<select name="cohorte_id">` en la barra de filtros.
- `docentes/tests.py` — tests nuevos y ajustados (detalle abajo).

## Resolución de cohorte con sesión

`_resolver_cohorte(param, comision)` (función pura, sin `request`) queda **sin cambios**: la siguen usando los tests que resuelven por parámetro explícito.

Nueva pieza central: `_resolver_cohorte_actual(request, disponibles)`. Implementa la cascada querystring → sesión → activa → primera de `disponibles`:

- `?cohorte=<id>` válido (matchea `disponibles`): se usa y se persiste en `request.session['cohorte_id']`.
- `?cohorte=<id>` inválido (no existe o no está en `disponibles`): cae derecho a la activa, **sin** consultar la sesión — mismo comportamiento "en silencio" que tenía `_resolver_cohorte` antes de que existiera la persistencia (lo verifica `test_cohorte_inexistente_cae_a_la_activa`, que sigue pasando sin tocar).
- Sin querystring: se lee `request.session['cohorte_id']`. Si la cohorte referenciada ya no existe (se borró), se hace `del request.session['cohorte_id']` y se sigue como si no hubiera sesión.
- Sin sesión (o recién limpiada): cae a `cohorte_activa()`; sin activa, a `disponibles[0]`.

Dos envoltorios delgados sobre esa función, cada uno con su propio cálculo de `disponibles`:

- `_resolver_cohorte_sesion(request, comision)` — usa `_cohortes_de_comision(comision)`. La llaman `comision_detail`, `estudiante_create`, `estudiantes_importar`, `parcial_create`, `estudiante_remove`, `estudiante_reinscribir_recursante`, `estudiante_reinscribir_pase`, `estudiantes_exportar` (los 8 sitios que antes llamaban a `_resolver_cohorte(request.GET.get('cohorte'), comision)` directamente). Misma forma de retorno `(cohorte, disponibles)`.
- `_resolver_cohorte_home(request)` — usa la nueva `_cohortes_del_docente(user)` (unión de cohortes con inscripciones en *cualquier* comisión del docente, más la activa — mismo criterio "incluir siempre la activa" que `_cohortes_de_comision`, para que el `<select>` nunca muestre una cohorte ausente de la lista). La llama `comisiones_list`.

Detalle deliberado: `cohorte_create` hace `request.session.pop('cohorte_id', None)` después de activar la nueva cohorte. Sin eso, si el docente tenía una cohorte vieja pinneada en sesión (posiblemente la que se acaba de cerrar), el panel seguiría mostrándola hasta una reselección manual — crear cohorte es justo la acción que debería "saltar" la vista a la nueva por default. Cubierto por `SesionCohorteTests.test_crear_cohorte_limpia_la_seleccion_pinneada`.

## Cómo quedó indicada la cohorte en `comision_detail`

`_selector_cohorte.html` (incluido igual que antes) ahora es solo un badge:

```
Cohorte: 2026 – C1 · en curso    [cambiar]
```

con `[cambiar]` linkeando al home. Debajo, se conserva sin cambios el aviso de "cohorte cerrada" (mismo texto, misma condición `cohorte_actual and not es_cohorte_activa`), porque sigue siendo lo que le explica al docente por qué no ve los formularios de alta — lo pedía el enunciado explícitamente.

`comision_detail` sigue pasando `cohorte_actual`, `cohortes_disponibles` y `es_cohorte_activa` al contexto (los tests existentes los siguen leyendo), pero dejé de pasar `siguiente_cohorte` y `cohorte_form`: ya no los usa ningún template de esa vista (el botón de crear se fue al home), así que quedaban muertos.

## Filtro de correcciones: independiente de la sesión

Elegí que `correccion_pendiente` **no** use `_resolver_cohorte_sesion`/la cohorte de sesión del punto 2. Es un parámetro GET propio (`cohorte_id`), con su propia lista de opciones (`_cohortes_del_docente`, o `_cohortes_de_comision` si hay una comisión filtrada) y su propio default (`cohorte_activa()`, no la de sesión).

Razón: esta pantalla ya cruzaba todas las cohortes **a propósito**, por diseño, antes de este cambio — es lo que permite corregirle a alguien que rinde un final de una camada anterior. Si el filtro heredara la cohorte de sesión, un docente que dejó el panel mirando una camada vieja en otro contexto (por ejemplo, revisando estadísticas históricas en `comision_detail`) entraría a corregir y no encontraría el trabajo del día a día — el caso de uso más común de esta pantalla — sin darse cuenta de por qué. Atar dos selecciones con propósitos distintos (una es "qué comisión estoy operando", la otra es "qué necesito corregir ahora, por default lo actual, con salida fácil a todo") las acopla de forma que puede sorprender. Un default fijo a la activa es predecible sin importar por dónde se navegó antes.

Implementación: `cohorte_id_presente = 'cohorte_id' in request.GET` distingue "no vino el parámetro" (default: activa) de "vino explícito" (incluyendo `cohorte_id=todas`, que es el valor del `<option>` "Todas las camadas" y con el que `cohorte_id_raw.isdigit()` da `False` → sin filtro). Esa distinción también se propaga a `filtros_query` para que paginar no pierda un "todas" explícito (si no, la página 2 perdería el parámetro y caería de nuevo al default).

El `<select>` de cohorte solo se muestra si hay más de una cohorte ofrecible (`cohortes_filtro_options|length > 1`), mismo patrón que el resto de los filtros de esta pantalla (comisión, práctica, ejercicio) — con una sola cohorte en juego, "todas" y "esa cohorte" son el mismo resultado, así que no hay nada que elegir.

## Tests

Tocados (los 4 que el enunciado anticipaba, más uno adicional forzado por el cambio de comportamiento):

- **`SelectorCohorteTests`**: sin cambios de fondo, sigue verificando exactamente lo mismo (default a la activa, override por querystring, `cohorte_inexistente` cae a la activa, prácticas no cambian entre cohortes, cohortes_disponibles por comisión, parciales filtran por cohorte). No hizo falta tocarlo: como el default sigue siendo "sin sesión → activa" y cada test usa un `self.client` fresco (sin sesión previa), el comportamiento observable no cambió.
- **`BloqueoCohorteCerradaTests`**, **`CohorteCreateTests`**, **`ReinscripcionEstudianteTests`**: revisados exhaustivamente por si algún test encadenaba dos requests en el mismo `self.client` donde una selección de sesión de la primera pudiera filtrarse a la segunda sin que el test lo esperara. Ninguno lo hace (son de un solo request por método, o los que hacen dos ya esperaban el resultado del segundo request explícitamente vía querystring). No requirieron cambios; quedaron como estaban.
- **`BadgeCohorteCorreccionTests`** (no estaba en la lista, pero entra en conflicto directo con el punto 3): su único test asumía que un intento de una cohorte vieja aparece **sin** filtro alguno — exactamente el comportamiento que el enunciado pide cambiar ("con el default en la activa, las correcciones pendientes de quien rinde un final dejan de verse hasta que el docente cambie el filtro. Es lo que se pidió"). Reescribí la clase con `setUp` compartido y 4 tests: default oculta la camada vieja, `?cohorte_id=todas` la muestra, filtro explícito por esa cohorte también la muestra, y la opción "Todas las camadas" está visible en el HTML incluso viendo el default.

Nuevos, para lo pedido explícitamente:

- **`SesionCohorteTests`** (clase nueva): persistencia en sesión en ambas direcciones (home → comisión, comisión → home), que el querystring actualiza la sesión para el próximo request (y puede volver a cambiarse), que una cohorte de sesión borrada cae a la activa sin romper y sin dejar la referencia colgada, y que crear una cohorte limpia el pin de sesión.
  - Nota de implementación: el test de "crear cohorte limpia la sesión" tuvo que evitar un `login()` de por medio para pinnear con un usuario y crear con otro, porque `django.contrib.auth.login()` flushea la sesión al cambiar de usuario autenticado — usar dos usuarios habría hecho pasar el test sin ejercitar el `pop()` de verdad. Quedó con un único superusuario haciendo las dos acciones.
- Ampliación de `BadgeCohorteCorreccionTests` (ver arriba) cubre el filtro de correcciones (default activa + "todas" muestra la vieja).

## Otras aristas

- Los `action="...?cohorte={{ cohorte_actual.pk }}"` en `comision_detail.html` (exportar, dar de baja, reinscribir) **no se tocaron**: siguen siendo redundantes con la sesión en el camino feliz (la sesión ya tiene ese valor), pero siguen siendo necesarios como el único mecanismo que le permite a los tests de guardas (`BloqueoCohorteCerradaTests`, etc.) forzar una cohorte distinta a la de sesión vía querystring explícito. Sacarlos habría dejado esas guardas sin forma de probarse desde un POST directo.
- `estudiantes_exportar`, `estudiante_remove` y las dos vistas de reinscripción son GET/POST-only sin re-render de `comision_detail.html`; usan `_resolver_cohorte_sesion` igual que las demás, así que también actualizan/leen sesión, consistente con el resto del panel.
- No se tocó `PASSWORD_HASHERS` en settings ni nada de performance de tests: noté que la suite tarda varios minutos en este entorno por el costo por-defecto de hashing de contraseñas en `_u()` (no hay un hasher rápido configurado para tests), pero es preexistente y ortogonal a este cambio — lo dejo mencionado por si en algún momento se quiere acelerar la suite.
