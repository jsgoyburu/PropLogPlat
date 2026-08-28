# Task 6 — reporte

**Procedencia.** El subagente escribió la implementación pero devolvió control
sin commitear ni reportar (patrón repetido en toda la ejecución). El controller
verificó y commiteó.

## Qué implementó

- `docentes/views.py` — `_require_cohorte_activa(cohorte)`, que lanza
  `PermissionDenied` si la cohorte es `None` o no está activa.
- `estudiante_create`, `estudiantes_importar` y `parcial_create` — resuelven la
  cohorte con `_resolver_cohorte` (la **seleccionada**, no la activa global) y
  aplican la guarda solo en `POST`.
- `_procesar_importacion_estudiantes` — firma `(archivo, comision, cohorte)`.
- Los `render()` de error de `estudiante_create` y `estudiantes_importar` ahora
  pasan `cohorte_actual` y `es_cohorte_activa`, y filtran sus queries de
  estudiantes por cohorte.
- `templates/docentes/comision_detail.html` — secciones de alta, importación y
  creación de parcial envueltas en `{% if es_cohorte_activa %}`.
- `docentes/tests.py` — `BloqueoCohorteCerradaTests`.

Reemplazó la guarda de `cohorte_activa() is None` que existía de una corrección
previa, en vez de dejarla al lado de la nueva.

## Comandos y salida

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test \
  docentes.tests.BloqueoCohorteCerradaTests \
  docentes.tests.SelectorCohorteTests \
  docentes.tests.CohorteCreateTests -v 1
Ran 19 tests in 103.074s
OK
```

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes -v 1
Ran 105 tests in 590.339s
OK
```

## Para el review

1. La guarda va solo en `POST`. Un `GET` a `estudiante_create` con una cohorte
   cerrada renderiza el panel sin el form (por el `{% if es_cohorte_activa %}`),
   que es lo buscado, pero conviene confirmar que no queda ninguna ruta `GET`
   que exponga el form.
2. `parcial_create` bloquea crear parciales en cohortes cerradas, pero cargar y
   editar notas de parciales existentes sigue habilitado a propósito. Verificar
   que `parcial_edit`, `parcial_notas` y `parcial_delete` no hayan quedado
   bloqueados por arrastre.
3. `_resolver_cohorte` lee `request.GET.get('cohorte')` incluso en las vistas
   POST: el form del panel tiene que propagar la cohorte seleccionada en el
   `action`, o un POST desde una cohorte cerrada resolvería a la activa. Vale
   verificar que el template lo haga.

---

# Arreglos del review

## Hallazgo 1 (Important) — `parcial_create` en GET mostraba el form

`parcial_form.html` es una plantilla aparte que no sabe de cohortes, así que
navegar a `?cohorte=<cerrada>` mostraba un formulario completo que solo iba a
fallar al enviarse. El GET ahora redirige al panel con un mensaje. El POST
sigue devolviendo 403, que es lo que corresponde a un envío directo al
endpoint: la guarda del GET lleva `request.method != 'POST'` justamente para
no comerse ese 403.

Test: `test_parcial_create_en_get_no_muestra_el_form_de_cohorte_cerrada`.

## Hallazgo 2 (Important) — faltaba cobertura del ocultamiento en el HTML

El brief pide dos cosas —el form no se renderiza **y** el POST rechaza— y solo
la segunda tenía tests. Agregados
`test_panel_de_cohorte_cerrada_no_renderiza_los_forms` y
`test_panel_de_cohorte_activa_si_renderiza_los_forms`.

## Hallazgo 3 (Minor) — comentario desactualizado

Reescrito. Y en el camino apareció algo peor: estaba escrito con `{# ... #}`
**multilínea**, sintaxis que Django solo soporta en una línea. El comentario se
venía renderizando como texto literal en el panel docente desde la Task 5.
Ahora usa `{% comment %}`. Lo detectó `test_alta_fallida_no_avisa_cohorte_cerrada`
por casualidad: el texto del comentario contenía la frase que ese test busca.

## Bug encontrado por el controller: notas de parcial cruzando camadas

`parcial_create` pre-creaba las `NotaParcial` desde
`comision.inscripciones.all()` sin filtrar por cohorte. Con el modelo de
cohortes andando, el primer parcial de la camada nueva habría nacido con una
fila de nota por cada estudiante de todas las camadas anteriores de esa
comisión — y esas notas alimentan las estadísticas de rendimiento. Ahora filtra
por `cohorte=cohorte`.

Test: `test_notas_precreadas_solo_para_la_camada_del_parcial`.

## Suite tras los arreglos

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes -v 1
Ran 109 tests in 498.652s
OK
```
