# Desbloqueo de ejercicios configurable por práctica

Fecha: 2026-08-06

## Problema

Hoy el desbloqueo de ejercicios es secuencial y está cableado en el código: dentro
de una práctica, el ejercicio N+1 sólo se habilita cuando el estudiante resuelve
correctamente el N. No hay forma de que un docente ofrezca una práctica con todos
los ejercicios abiertos desde el inicio.

El desbloqueo secuencial sirve para prácticas que construyen dificultad de forma
acumulativa, pero para prácticas de repaso o de ejercitación libre funciona como
un umbral innecesario: un estudiante que se traba en el ejercicio 2 no puede
practicar el 5, aunque el 5 no dependa del 2.

## Solución

Un interruptor por `PracticaComision` que elige entre dos modos:

- **secuencial** (default, comportamiento actual): el ejercicio N+1 se habilita al
  resolver el N.
- **libre**: todos los ejercicios de la práctica están disponibles desde el inicio.

El interruptor vive en `PracticaComision` —no en `Practica`— por consistencia con
`fecha_apertura` / `fecha_cierre`, que ya son propiedades de la asignación a una
comisión y no de la práctica canónica. Una misma práctica del banco común puede
así ser secuencial en una comisión y libre en otra, y el modo no viaja al importar.

Se implementan sólo estos dos modos. Un `BooleanField` cubre el caso; si en el
futuro aparece un modo intermedio (p.ej. "N ejercicios abiertos a la vez"), migrar
a `CharField` con choices es una migración trivial.

## Modelo de datos

Campo nuevo en `ejercicios.models.PracticaComision`:

```python
desbloqueo_secuencial = models.BooleanField(
    default=True,
    verbose_name='desbloqueo secuencial',
    help_text=(
        'Si está marcado, cada ejercicio se habilita al resolver correctamente '
        'el anterior. Si no, todos los ejercicios están disponibles desde el inicio.'
    ),
)
```

Migración simple en `ejercicios/migrations/`, sin data migration: el `default=True`
deja todas las prácticas existentes en el comportamiento actual.

No se agregan campos a `Progreso`. En modo libre `Progreso` sigue existiendo y
manteniéndose actualizado (ver "Progreso"), lo que permite alternar de modo a
mitad de cursada sin dejar datos inconsistentes.

## Dependencia

Este trabajo va **después** de `2026-08-06-panel-resuelto-vs-revisado-design.md`,
que crea el módulo compartido `ejercicios/correctitud.py` y la columna `Resuelto`
del panel docente. Ambas cosas se dan por existentes acá.

## Definición de "ejercicio resuelto"

Varios puntos del sistema necesitan la misma pregunta: *¿este estudiante ya
resolvió este `EjercicioPractica`?* Hoy `ejercicio_detail` la responde con un
criterio propio (correcto y no rechazado por docente) y la aprobación docente de
un intento incorrecto agrega otro caso.

Se usa el `Q_CORRECTO` de `ejercicios/correctitud.py` —la correctitud efectiva que
ya usaban analíticas y el servidor MCP, y que el PR previo centralizó:

> Un EP está **resuelto** para un estudiante si existe algún `Intento` suyo sobre
> ese EP con `aprobado_docente=True`, o con `es_correcto=True` y sin revisar.

Es lógicamente equivalente al criterio "correcto o aprobado, y no rechazado", y
preserva el comportamiento actual para el caso frecuente: un correcto rechazado
por el docente deja de contar como resuelto.

**Cambio de comportamiento deliberado.** El predicado se aplica también a
`ya_resuelto` en `ejercicio_detail`. Hoy, si un docente aprueba a mano un intento
incorrecto, el estudiante puede seguir enviando respuestas a ese ejercicio: el
progreso avanza pero el ejercicio no cuenta como resuelto. Con el predicado
unificado deja de admitir envíos, igual que cualquier otro ejercicio resuelto.
Es un arreglo de una inconsistencia preexistente, decidido explícitamente como
parte de este trabajo.

## Módulo nuevo: `ejercicios/progreso.py`

Hoy la lógica de avance de `Progreso` está duplicada en dos lugares casi idénticos:

- `ejercicios/api/views.py` → `IntentoCreateView._avanzar_progreso`
- `docentes/views.py` → `_avanzar_progreso_por_aprobacion_docente`

Agregar un segundo modo a ambas copias multiplicaría la duplicación. Se extrae un
módulo `ejercicios/progreso.py` con estas funciones públicas:

```python
def eps_resueltos(estudiante, practica) -> set[int]:
    """Ids de los EjercicioPractica de `practica` ya resueltos por `estudiante`."""

def esta_resuelto(estudiante, ep) -> bool:
    """El predicado de arriba para un único EjercicioPractica."""

def avanzar_progreso(estudiante, ep, *, secuencial: bool) -> tuple[bool, int]:
    """Actualiza el Progreso tras resolverse `ep`.

    Devuelve (practica_completa, ejercicios_pendientes).
    """
```

`eps_resueltos` aplica el predicado a toda la práctica en una sola query, para que
el recálculo del modo libre no dispare una consulta por ejercicio.

`avanzar_progreso` toma el lock pesimista (`select_for_update`) y hace:

- **modo secuencial**: la lógica actual sin cambios — si
  `progreso.ejercicio_practica_actual == ep`, avanzar al siguiente por `orden`
  (`None` si no hay siguiente); si no, no hacer nada.
- **modo libre**: recalcular `ejercicio_practica_actual` como el primer EP de la
  práctica, por `orden`, que **no** esté en `eps_resueltos`; `None` si están todos
  resueltos.

El segundo elemento del retorno, `ejercicios_pendientes`, es la cantidad de EPs no
resueltos que quedan tras este intento. En modo secuencial se devuelve derivándolo
del `orden` del ejercicio actual; en modo libre sale directo de `eps_resueltos`.

Ambos call sites pasan a invocar `avanzar_progreso(...)`, cada uno leyendo el modo
de su `PracticaComision`. Las funciones viejas se eliminan.

El recálculo en modo libre es lo que mantiene `Progreso` coherente cuando el
estudiante resuelve fuera de orden: sin él, `ejercicio_practica_actual` quedaría
clavado en el primer ejercicio y `practica_completa` nunca se dispararía.

## Vistas de estudiante (`ejercicios/views.py`)

**`practica_detail`** — el cálculo de estados por intento (aprobado / pendiente /
rechazado) no cambia. Cambia sólo el flag `desbloqueado`:

```python
desbloqueado = (
    not pc.desbloqueo_secuencial
    or practica_marcada_completa
    or (ep_actual_orden is not None and ep.orden <= ep_actual_orden)
)
```

En modo libre ningún EP queda en estado `'bloqueado'`: los que no tienen intentos
se muestran como `'actual'`.

**`ejercicio_detail`** — en modo libre se saltea el bloque que consulta `Progreso`
para decidir acceso y se resuelve directo:

```python
ya_resuelto = esta_resuelto(usuario, ep)   # predicado unificado

if not pc.desbloqueo_secuencial:
    puede_enviar = not ya_resuelto
else:
    ...  # lógica actual, incluidos los redirects
```

Desaparecen así los dos `redirect` por orden, que en modo libre no aplican. La
vista pasa `pc.desbloqueo_secuencial` al contexto del template.

## API (`ejercicios/api/views.py`)

`IntentoCreateView` **no** bloquea intentos por orden (sólo por inscripción y por
fechas), así que no hay gating nuevo que agregar. Los cambios son:

- `_avanzar_progreso` se reemplaza por
  `avanzar_progreso(request.user, ep, secuencial=pc.desbloqueo_secuencial)`,
  usando el `pc` que la vista ya resolvió unas líneas antes.
- La respuesta suma el campo `ejercicios_pendientes` (int) junto al
  `practica_completa` que ya devuelve.

## Aprobación docente (`docentes/views.py`)

`_avanzar_progreso_por_aprobacion_docente` se reemplaza por la llamada compartida.
El modo se lee de `intento.practica_comision.desbloqueo_secuencial`; si
`practica_comision` es `None` (intentos viejos anteriores a esa FK), se asume
`secuencial=True`.

## Panel docente: ocultar "Ej. N" en prácticas libres

En `comision_detail.html`, la fila de cada práctica por estudiante muestra `Ej. N`
(el `ejercicio_actual` según `Progreso`) en la columna `Detalle`. En modo libre ese
número cambia de significado: pasa a ser "el primer ejercicio que todavía no
resolvió". Un estudiante que resolvió el 2, 3 y 4 pero no el 1 aparecería como
`Ej. 1`, que se lee como si no hubiera trabajado.

El contador `N/M resueltos` que hace falta acá **ya lo aporta el PR previo**
(`2026-08-06-panel-resuelto-vs-revisado-design.md`), que agrega la columna
`Resuelto` con ese dato para todas las prácticas. Este trabajo sólo tiene que
evitar que el `Ej. N` engañe cuando la práctica es libre:

- `practicas_detalle` suma la clave `desbloqueo_secuencial`.
- En la columna `Detalle`, la rama `{% elif detalle.ejercicio_actual %}` se
  condiciona a que la práctica sea secuencial. En prácticas libres esa celda queda
  vacía y la información de avance la da la columna `Resuelto`.
- El badge `completa` y la rama `sin ejercicios` no cambian en ningún modo.

## Mensaje al estudiante tras un intento correcto

`templates/ejercicios/ejercicio.html` muestra hoy "¡Correcto! Avanzás al siguiente
ejercicio." En modo libre eso es falso: no se desbloqueó nada porque ya estaba todo
abierto. El bloque aparece tres veces (una por tipo de ejercicio) y las tres se
actualizan igual.

En modo libre el texto pasa a usar `ejercicios_pendientes` de la respuesta de la API:

- `> 1` → "¡Correcto! Te quedan N ejercicios por resolver."
- `== 1` → "¡Correcto! Te queda 1 ejercicio por resolver."
- `== 0` → no aplica: se muestra el cartel existente de "¡Práctica completa!".

El link "Volver a la práctica →" se mantiene en todos los casos. En modo secuencial
el texto no cambia.

## Casos borde

**Estudiante en dos comisiones con la misma práctica y modos distintos.** Cada
cursado tiene su propia fila de progreso: la vista web usa el `pc` de la URL y la
API lo recibe explícito, así que cada comisión respeta su modo y su puntero.

Esto **no era así cuando se escribió este spec**. `Progreso` era único por
`(estudiante, practica)`, de modo que dos comisiones que compartieran una misma
`Practica` canónica compartían una sola fila: un intento en una movía el puntero
que leía la otra. Era preexistente, pero hacer configurable el desbloqueo lo
ensanchaba, porque las dos comisiones pasaban a poder aplicar reglas distintas
sobre la fila compartida.

Se resolvió dentro de este mismo trabajo, en un tramo aparte: `Progreso` pasó a
tener clave `(estudiante, practica_comision)`, con migraciones `0023`–`0026` que
incluyen el backfill y la reatribución de los intentos que la `0015` había
asignado a ciegas. `eps_resueltos` y `esta_resuelto` acotan por comisión, y
`avanzar_progreso` recibe el `pc` en vez del flag de modo.

`ProgresoCruzadoEntreComisionesTests` en `ejercicios/tests.py` afirma ahora lo
contrario de lo que afirmaba: que las dos comisiones **no** comparten progreso.

**Cambio de libre a secuencial a mitad de cursada.** Como en modo libre el
`Progreso` se mantiene recalculado, al volver a secuencial `ejercicio_practica_actual`
ya apunta al primer ejercicio sin resolver. No se re-bloquea nada que el estudiante
haya resuelto, y los ejercicios resueltos salteados conservan su estado por intento.

**Cambio de secuencial a libre.** Se abre todo inmediatamente; el `Progreso`
existente sigue siendo válido y se recalcula en el siguiente intento correcto.

**Práctica sin ejercicios.** Sin cambios: `eps` vacío, no se entra al loop.

## Formulario docente

`PracticaComisionForm` (`docentes/forms.py`) suma `desbloqueo_secuencial` a
`fields`, con label explicativo:

> "Desbloqueo secuencial: cada ejercicio se habilita al resolver el anterior.
> Desmarcá esta opción para que todos los ejercicios estén disponibles desde el inicio."

El campo se renderiza en los templates donde ya aparecen `fecha_apertura` /
`fecha_cierre` (formularios de asignar y editar práctica en comisión).

## Tests

En `ejercicios/tests.py`, extendiendo `DesbloqueoProgresivoTests`:

- Modo libre: `practica_detail` no devuelve ningún EP en estado `'bloqueado'`.
- Modo libre: `ejercicio_detail` de un ejercicio avanzado responde 200 con
  `puede_enviar=True` (hoy redirige).
- Modo libre: resolver el ejercicio 3 sin haber resuelto el 1 deja
  `ejercicio_practica_actual` en el ejercicio 1.
- Modo libre: resolver el último ejercicio pendiente devuelve
  `practica_completa=True` y deja `ejercicio_practica_actual=None`.
- Modo libre: la API devuelve `ejercicios_pendientes` correcto tras resolver
  fuera de orden.
- Modo secuencial: los tests existentes siguen pasando sin modificarse (regresión).
- Predicado unificado: un ejercicio con intento incorrecto aprobado por el docente
  queda con `puede_enviar=False` (cambio de comportamiento deliberado).
- Predicado unificado: un intento correcto rechazado por el docente sigue
  admitiendo envíos (no cambia).

En `docentes/tests.py`:

- Modo libre + aprobación docente de un intento incorrecto: el progreso se recalcula.
- `comision_detail` no muestra `Ej. N` en prácticas libres y sí en secuenciales.
- `PracticaComisionForm` acepta y persiste el campo; el default es `True`.

## Documentación

Actualizar los docstrings que describen el desbloqueo como si fuera siempre
secuencial: `Progreso` y `EjercicioPractica` en `ejercicios/models.py`, y los de
`practica_detail` / `ejercicio_detail` en `ejercicios/views.py`.

Esos docstrings citan "AGENTS.md §7" para las reglas de desbloqueo, pero la §7
actual de AGENTS.md trata de analítica educativa: la referencia quedó desactualizada
por una renumeración previa. Se reemplaza la cita por la descripción de las reglas
en el propio docstring, sin tocar AGENTS.md ni perseguir la renumeración (fuera de
alcance).

## Fuera de alcance

- Modos de desbloqueo adicionales (por fecha, por ventana de N ejercicios).
- Configurar el modo a nivel `Practica` canónica.
- Resolver la ambigüedad de la API cuando un estudiante está en dos comisiones con
  la misma práctica (preexistente, afecta también a las fechas).
- Actualizar el comando histórico `reconciliar_V_mayuscula`.
- Las métricas del panel docente: las cubre el PR previo, y el badge `completa`
  sigue midiendo revisión docente a propósito.
