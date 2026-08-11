# Historial del estudiante separado por cohorte

El historial agrupa los intentos por cohorte, para que el estudiante pueda
comparar su rendimiento entre camadas.

Base: rama `claude/historial-por-cohorte`, sacada de
`claude/desbloqueo-configurable` en `8817c80`. Se apila sobre el modelo de
cohorte (`71e4391`, `a1fb998`, `8ee8b54`) y sobre el aislamiento del read path
(`60edc47`, `8817c80`); no se puede mergear antes que ellos.

## Problema

`mi_historial` agrupa los intentos en un dict keyeado por
`ejercicio_practica_id` solo:

```python
ep_id_actual = intento.ejercicio_practica_id
if ep_id_actual not in grupos_por_ep:
    grupo = {..., 'ultimo_intento': intento, 'intentos_anteriores': []}
```

Un recursante tiene intentos del mismo `EjercicioPractica` en dos cohortes. Con
esa clave, las dos camadas **colapsan en un solo grupo**: `ultimo_intento` sale
de la que ordene primero y los intentos de la camada anterior caen en
`intentos_anteriores` como si fueran parte de la misma corrida. El historial no
es que no separe las camadas — las mezcla y presenta el resultado como una
secuencia continua.

Es el mismo defecto de fondo que `60edc47` arregló en el resto del read path
(`home`, `practica_detail`, `ejercicio_detail`), que quedó fuera de aquel
alcance porque el code review original no lo listó.

### La duplicación que hay debajo

La lógica de agrupación está escrita dos veces:

- `ejercicios/views.py::mi_historial` — inline, para la vista propia del
  estudiante.
- `docentes/views.py::_build_estudiante_intentos_context` — helper, para
  `docentes:estudiante_detail`.

Hay una tercera copia del enriquecido en `docentes/views.py::correccion_pendiente`,
que arma `diccionario_con_valores` por su cuenta. No agrupa por ejercicio ni
muestra historial, así que el defecto de cohorte no la alcanza y queda fuera de
alcance; se anota porque es el próximo candidato obvio si alguna vez se
consolida el enriquecido entero.

Las dos alimentan el mismo template, `docentes/estudiante_detail.html`,
distinguido por el flag `vista_propia_estudiante`. Pero **no producen el mismo
contexto**: la versión del estudiante no calcula `diccionario_con_valores`, que
el helper del docente sí arma para los ejercicios `determinacion_verdad`. El
template ramifica sobre ese atributo:

```
{% if grupo.ultimo_intento.diccionario and not grupo.ultimo_intento.diccionario_con_valores %}
```

de modo que el estudiante mirando su propio intento de `determinacion_verdad`
cae en la rama degradada y ve su respuesta peor renderizada que el docente
mirando ese mismo intento. Es un bug preexistente, independiente de cohortes.

Aplicar el cambio de cohorte sobre las dos copias lo perpetuaría y duplicaría
la superficie de test. La unificación va primero.

## Diseño

### 1. Unificar la agrupación en `ejercicios/historial.py`

Mover `_build_estudiante_intentos_context` a un módulo nuevo, `ejercicios/historial.py`,
y que las dos vistas lo llamen.

La dirección de la dependencia es la correcta: los datos son `Intento`, modelo
de `ejercicios`, y `docentes` ya importa modelos de `ejercicios`. Sigue el
precedente de `cursos/cohortes.py`, que existe justamente para que `ejercicios`
pueda importarlo sin ciclo.

`mi_historial` queda reducido a resolver las comisiones del estudiante, delegar
y renderizar. El bug de `diccionario_con_valores` desaparece como consecuencia
de la unificación, no como parche aparte.

### 2. Agrupar por `(cohorte, ejercicio_practica)`

La clave del dict pasa de `ep_id` a la tupla `(cohorte_id, ep_id)`. Es el
arreglo del defecto de conflación.

El `order_by` antepone la cohorte descendente, para que las camadas salgan
contiguas y la más reciente primero:

```python
.order_by('-cohorte__anio', '-cohorte__cuatrimestre',
          'practica_comision__comision__nombre',
          'practica_comision__orden',
          'ejercicio_practica__orden', '-timestamp')
```

`Cohorte.Meta.ordering` (`['-anio', '-cuatrimestre']`) no se aplica sola al
atravesar la FK desde `Intento`, por eso el orden va explícito. `'cohorte'` se
suma al `select_related`: sin eso cada encabezado de sección dispara una query.

`Intento.cohorte` es NOT NULL desde `ejercicios/migrations/0028_cohorte_not_null.py`,
así que no hay caso de intento sin cohorte que contemplar.

### 3. Contexto anidado

El helper devuelve, en lugar de la lista plana `intentos_agrupados`:

```python
historial_por_cohorte = [
    {'cohorte': <Cohorte>, 'grupos': [ ...grupos de esa camada... ]},
    ...
]
```

Se anida explícitamente en vez de usar `{% ifchanged %}` sobre la lista plana:
el diseño pide secciones con envoltorio y `ifchanged` no da un punto donde
cerrar el `<div>`. Además deja una superficie de aserción limpia para los tests.

El template gana un `for` externo con el encabezado `{{ item.cohorte }}` — que
ya renderiza como `2026 – C1` por el `__str__` del modelo — y el `for` interno
sobre `item.grupos` queda igual que hoy.

El encabezado se muestra **siempre**, tenga el estudiante una camada o cinco:
un solo camino de código, sin condicionales, y la vista queda autodocumentada.

### Alcance: las dos vistas

Las secciones por cohorte aplican también a `docentes:estudiante_detail`. El
defecto de agrupación está en el armado de los grupos, que ambas vistas
comparten; arreglarlo solo del lado del estudiante dejaría al docente viendo un
historial conflacionado justo donde más engaña, al evaluar a un recursante.
Evita además ramificar el template con `vista_propia_estudiante`.

## Tests

Sobre un recursante con intentos del mismo ejercicio en dos camadas:

- se arman **dos** grupos y no uno;
- cada `ultimo_intento` es el de su cohorte;
- las secciones salen ordenadas con la camada reciente primero;
- con una sola cohorte, la sección sigue apareciendo con su encabezado.

Los mismos asserts corren contra las dos vistas, ya que comparten helper.

Los ids de `Cohorte` se crean al revés del orden cronológico real, como en
`RecursanteReadPathTests`: si algún query cae por accidente en "el último por
id gana", el orden invertido lo expone en vez de taparlo.

Cada test se verifica en rojo antes de aplicar el cambio de agrupación.

## Fuera de alcance

- No se agrega un `<select>` de cohorte a la barra de filtros. La comparación
  es por secciones visibles, no por alternancia de filtro.
- No se calculan métricas agregadas por cohorte (resueltos, intentos promedio).
  Si después se quieren, entran sobre esta estructura sin rehacerla.
- No se toca la vista docente más allá de lo que trae compartir el helper.
