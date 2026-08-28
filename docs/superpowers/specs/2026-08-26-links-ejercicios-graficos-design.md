# Links al ejercicio desde los gráficos de analíticas

Fecha: 2026-08-26

## Objetivo

Que todo gráfico cuyo eje X sean ejercicios permita abrir cada ejercicio, y que
se pueda ver de cuál se trata sin salir de la página.

El disparador fue concreto: en la página de investigación las etiquetas dicen
`EP 16 [7]`. Ese número no le dice nada a nadie. Un docente que ve una barra de
abandono al 40% no tiene forma de saber qué ejercicio la produjo.

## Estado actual

Las **tablas** de esas mismas secciones ya enlazan al ejercicio:

```django
<a href="{% url 'ejercicios:ejercicio' r.pc_id r.ep_id %}"
   title="{{ r.enunciado_corto }}" target="_blank">EP {{ r.ep_id }}</a>
```

Los gráficos, no. La información existe y el patrón existe; solo no llegó al
`<canvas>`.

`ejercicios:ejercicio` toma `(pc_id, ep_id)` —
`practica/<int:pc_id>/ejercicio/<int:ep_id>/` — y muestra el ejercicio dentro de
su práctica.

## Alcance

Cinco gráficos. El inventario se hizo revisando los 21 `new Chart(...)` de las
tres páginas de analíticas, no por muestreo.

| Gráfico | Página | Datos |
|---|---|---|
| C1 · Intentos hasta correcto | investigación | ya trae `ep_id`, `pc_id`, `enunciado_corto` |
| B2 · Persistencia relativa | investigación | idem |
| D1 · Abandono local por EP | investigación | idem |
| 🔴 Ejercicios más difíciles | dashboard | falta `ep_id` y `pc_id` |
| 📊 Distribución de intentos | dashboard | falta `ep_id` y `pc_id` |

Las tres de investigación ya vienen enriquecidas por `_enrich` dentro de la
vista `investigacion`, que es de donde las tablas sacan sus links.

### Fuera de alcance, y por qué

- **A · Tasa de entrada efectiva** (`chart-entrada`): su eje son **prácticas**,
  no ejercicios. La etiqueta es `practica_titulo`.
- **C2 · Desacople docente-máquina** (`chart-desacople`): doughnut de tres
  categorías fijas (acuerdo / motor ok / docente ok). No hay ejercicio al que ir.
- **Drill-down por ejercicio** (`chart-drill`): ya es *de* un solo ejercicio; su
  eje son perfiles de convergencia, no ejercicios.
- Los ~12 gráficos demográficos (NSE, facultades, carreras, cohortes, pandemia,
  correlaciones) y el de evolución temporal: no refieren a ejercicios.
- El panel docente (`templates/docentes/`): queda fuera, como en el trabajo de
  filtros.

## Decisiones tomadas

1. **Destino**: `ejercicios:ejercicio` — el ejercicio dentro de su práctica, tal
   como lo ve el estudiante. Es lo que ya usan las tablas, así que gráfico y
   tabla coinciden en vez de ofrecer dos destinos distintos para el mismo dato.
2. **Interacción**: click sobre la barra **o** sobre su etiqueta abre el
   ejercicio en pestaña nueva; el cursor cambia a mano sobre las zonas activas;
   el tooltip muestra el enunciado.
3. **La URL se arma en Python**, no en JavaScript.

## Arquitectura

### La URL viaja en los datos

Cada fila que alimenta un gráfico lleva una clave `url`: la ruta ya resuelta, o
`None` cuando no hay práctica visible para ese ejercicio.

La alternativa era emitir una plantilla de URL y reconstruirla en JS con reemplazo
de placeholders. Se descarta: duplica el ruteo de Django en el front y se rompe
en silencio si `ejercicios/urls.py` cambia — el link seguiría existiendo,
apuntando a ninguna parte. Con la URL resuelta en el servidor, un cambio de ruta
se propaga solo.

Es el mismo criterio que ya sigue `filtros.qs`.

### Helper compartido en JS

Los cinco gráficos usan la misma mecánica, así que se escribe una vez:

```js
function enlazarEjerciciosDelEje(chart, filas) { ... }
```

Responsabilidades:

- `onClick`: resuelve el índice de la barra o de la etiqueta y abre `filas[i].url`
  en pestaña nueva. Si `url` es `None`, no hace nada.
- `onHover`: `cursor: pointer` solo sobre índices con `url`.
- callback de tooltip: antepone `enunciado_corto` al valor.

Detectar el click sobre la **etiqueta** —que cae fuera del área del gráfico— usa
`chart.scales.x.getValueForPixel(evt.x)`, que es la vía documentada de Chart.js.
En los gráficos horizontales del dashboard (`indexAxis: 'y'`) el eje de
categorías es `chart.scales.y` y la coordenada es `evt.y`: el helper resuelve cuál
usar leyendo la config del chart, en vez de asumir orientación.

El helper vive en un `<script>` compartido y las tres páginas lo cargan. Hoy cada
template repite su propio `parseData`/`noData`; no se refactoriza eso — es ruido
ajeno a este cambio.

### Cambios en Python

**`analiticas/views.py`**

- `_ejercicios_mas_dificiles`: ya itera sobre objetos `EjercicioPractica`
  (`for ep in eps`), así que `ep.id` está a mano; hoy solo emite
  `ejercicio_id`. Se agregan `ep_id` y `url`.
- `_distribucion_intentos`: se agregan `ep_id` y `url`.
- Un helper `_url_ejercicio(ep_id, comision_ids)` resuelve el `PracticaComision`
  y arma la ruta con `reverse`, en un solo lugar.
- La vista `investigacion` ya calcula `pc_id` en `_enrich`; se le agrega `url`
  ahí mismo para que las tres secciones queden con la misma clave que las dos del
  dashboard.

## El caso que puede salir mal

En el dashboard un ejercicio puede pertenecer a una práctica asignada a **varias**
comisiones, y esos gráficos agregan todas las comisiones visibles. No existe un
`pc_id` único.

Regla: se toma el `PracticaComision` de **menor `id`** entre las comisiones
filtradas. Es determinística —dos cargas dan el mismo link— y el ejercicio que se
abre es el mismo en cualquier caso; solo cambia la práctica que lo enmarca.

Cuando el docente filtra a una sola comisión, cosa que ahora se puede, la
ambigüedad desaparece.

Si un ejercicio no tiene ningún `PracticaComision` visible para ese usuario,
`url` es `None` y la barra no reacciona: mejor una barra inerte que un link a un
404 o, peor, a la práctica de otra comisión.

## Accesibilidad

Un `<canvas>` no es navegable por teclado y esto no lo cambia. La mitigación es
que **las tablas de datos siguen ahí**: cada una de las tres secciones de
investigación tiene su `<details> Ver tabla de datos` con links reales, y los dos
paneles del dashboard tienen su tabla equivalente. Quien no pueda usar el mouse
llega al mismo lugar por esa vía.

Se deja anotado, no resuelto: hacer los ejes realmente accesibles pide sacar las
etiquetas del canvas, que es un rediseño de otra escala.

## Tests

- `_url_ejercicio`: devuelve la ruta correcta; `None` cuando el ejercicio no
  tiene práctica visible; el mismo `pc_id` de forma estable cuando hay varias
  comisiones candidatas.
- Los cinco datasets incluyen `url` cuando corresponde.
- Sobre el **HTML servido**, no sobre el contexto: el `json_script` de cada
  gráfico lleva las urls. Sigue el patrón de
  `test_links_de_exportacion_llevan_el_filtro_en_el_html`, que ya existe y que
  atrapó una regresión que un test sobre el contexto habría dejado pasar.
- Un ejercicio sin práctica visible produce `url: null` y no rompe el render.

Sin migraciones. Sin dependencias nuevas.

## Fuera de alcance

- Refactorizar `parseData`/`noData`, duplicados entre templates.
- Hacer los ejes del canvas navegables por teclado.
- Los gráficos del panel docente.
