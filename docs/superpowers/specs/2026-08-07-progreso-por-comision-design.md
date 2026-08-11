# Progreso por comisión

Cambia la clave de `Progreso` de `(estudiante, practica)` a
`(estudiante, practica_comision)`.

Base: rama `claude/desbloqueo-configurable` (PR #187). Este trabajo se apila
sobre ese PR y no se puede mergear antes que él.

## Problema

`Practica` es la entidad canónica y `PracticaComision` la asigna a una comisión.
Importar una práctica no la copia: crea un `PracticaComision` apuntando a la
práctica original. Dos comisiones pueden entonces compartir la misma `Practica`.

`Progreso` tiene `unique_together = ['estudiante', 'practica']`. Un estudiante
inscripto en dos comisiones que comparten una práctica lee y escribe **una sola
fila** desde ambas. Un intento hecho en una mueve el puntero
`ejercicio_practica_actual` que lee la otra.

El PR #187 lo agravó: cada `PracticaComision` tiene ahora su propio
`desbloqueo_secuencial`, así que las dos comisiones aplican reglas distintas
sobre la fila compartida. Antes al menos aplicaban la misma.

El bleed no se limita a `Progreso`. `esta_resuelto()` y el subquery de "último
intento" de `practica_detail` filtran por `ejercicio_practica` sin acotar por
comisión, así que el estado visible (aprobado / pendiente / rechazado) también
cruza. Y en analíticas, `completaron_map` y `practicas_completadas` cuentan una
práctica completada una vez por cada comisión en la que esté el estudiante,
desde una única fila de `Progreso`.

### La adivinanza del write path

`POST /api/intentos/` recibe solo `ejercicio_practica_id` y deduce la comisión:

```python
pc = (PracticaComision.objects
      .filter(practica=ep.practica, comision__estudiantes=request.user)
      .first())
```

Hoy ese `.first()` elige nada más que el modo de desbloqueo. Con `Progreso`
keyeado por `practica_comision` elegiría **qué fila avanzar**, y para el
estudiante que este cambio pretende arreglar es una moneda al aire. El contrato
de la API tiene que llevar el `pc`; si no, la clave nueva es inaplicable en el
punto de escritura.

## Estado de los datos

No hay comisiones con estudiantes compartidos. El conjunto ambiguo está vacío
hoy, así que el backfill no es el punto difícil: es casi mecánico. El valor del
cambio no está en arreglar datos viejos sino en que el runtime deje de poder
generar el problema — nada impide hoy inscribir a un estudiante en dos
comisiones que comparten una práctica, y con `desbloqueo_secuencial` el daño
sería silencioso.

No se pudo verificar ese supuesto contra la base de producción: el classifier
del entorno bloqueó `railway run ... manage.py shell`. El diseño lo compensa
haciendo que la migración `0026` falle ruidosamente si el supuesto no vale
(ver "Riesgos").

## Decisiones

| Decisión | Elección | Razón |
|---|---|---|
| Backfill ambiguo (n≥2) | Reconstruir desde `Intento` | Conjunto vacío hoy; se escribe la regla semánticamente correcta y se cubre con unitarios |
| Contrato de la API | `practica_comision_id` requerido | Elimina toda ruta de adivinanza; el template ya tiene `pc.id` |
| Alcance del read path | Completo | `Progreso` correcto con la UI mostrando otra comisión deja el trabajo a mitad |
| `Progreso.practica` | Se elimina | Derivable; además simplifica dos consultas de analíticas y corrige el doble conteo |
| `Intento.practica_comision` | `null=False` | Convierte el supuesto en algo que verifica la base |

## Modelo

```python
class Progreso(models.Model):
    estudiante = FK(AUTH_USER_MODEL, related_name='progresos')
    practica_comision = FK(PracticaComision, related_name='progresos')
    ejercicio_practica_actual = FK(EjercicioPractica, SET_NULL, null=True)

    class Meta:
        unique_together = ['estudiante', 'practica_comision']
```

`Intento.practica_comision` pasa a `null=False`. El invariante
`practica_comision.practica == ejercicio_practica.practica`, ya documentado en
`Intento`, aplica igual a `Progreso`.

El docstring de `Progreso` se actualiza: hoy dice "una fila por par
`(estudiante, practica)`" y describe el modo secuencial y el libre sin
mencionar que el modo sale del `PracticaComision`.

## Migraciones

Cuatro archivos separados. `0024` es `RunPython` puro y las demás son schema
puro: separarlas evita mezclar `ALTER TABLE` con INSERTs de FK deferred en la
misma transacción, que es lo que obligó a `atomic = False` en la `0015`.

| # | Contenido |
|---|---|
| 0023 | `AddField Progreso.practica_comision`, `null=True` |
| 0024 | `RunPython`: backfill de `Intento` y después de `Progreso` |
| 0025 | `Progreso.practica_comision` → `null=False`; `AlterUniqueTogether`; `RemoveField practica` |
| 0026 | `Intento.practica_comision` → `null=False` |

En la `0025`, `AlterUniqueTogether` tiene que ir **antes** de `RemoveField`: el
`unique_together` viejo referencia `practica`. El autodetector de Django lo
ordena así, pero se verifica en el archivo generado.

Las reglas de atribución de la `0024` viven en `ejercicios/backfill.py` como
funciones puras que reciben las clases de modelo por parámetro, para que la
migración las invoque con `apps.get_model(...)` y los tests con los modelos
reales (ver "Tests").

### Backfill de `Intento` (primero)

`Progreso` depende de esta atribución, así que corre antes. Para cada `Intento`
con `practica_comision` en NULL, por orden de regla:

1. PCs de `ejercicio_practica.practica` donde el estudiante está inscripto →
   si hay exactamente 1, se usa.
2. Si hay 0 (estudiante desinscripto): PCs de esa práctica en total → si hay
   exactamente 1, se usa.
3. Si sigue ambiguo, queda en NULL y la `0026` falla.

La regla 1 es "inscripción única", no "cualquier pc de la práctica", porque
este es el paso peligroso del PR: atribuir mal un intento le saca a un
estudiante un ejercicio que ya resolvió.

### Backfill de `Progreso`

Para cada fila, los PCs candidatos son los de `progreso.practica` donde el
estudiante está inscripto. Sea `n` esa cantidad:

- **n = 1** — se asigna el pc y `ejercicio_practica_actual` se conserva
  verbatim. Sin reconstrucción y sin regresión. Es el caso de todos los datos
  actuales.
- **n = 0** — fila inalcanzable (práctica desasignada, o estudiante
  desinscripto). Se borra.
- **n ≥ 2** — se abre en `n` filas. El puntero de cada una se reconstruye desde
  los intentos ya atribuidos a ese pc con `Q_CORRECTO`, como *primer
  `EjercicioPractica` por `orden` sin resolver* — el mismo recálculo que
  `avanzar_progreso` hace en modo libre. `None` si están todos resueltos.

La migración reporta por consola cuántas filas cayó en cada rama.

Reversa: `migrations.RunPython.noop`. Volver atrás desde el esquema nuevo
requiere colapsar `n` filas en una y no hay criterio para elegir el puntero
ganador; el rollback real es restaurar backup.

## Write path

`ejercicios/progreso.py`:

```python
def avanzar_progreso(estudiante, ep, pc) -> tuple[bool, int]:
```

Se va el kwarg `secuencial`: sale de `pc.desbloqueo_secuencial`. Deja de ser
posible pasar un modo que no corresponda al pc. La función asegura
`pc.practica_id == ep.practica_id` y el `get_or_create` / `select_for_update`
pasa a keyear por `(estudiante, practica_comision)`.

`ejercicios/api/views.py` — `IntentoInputSerializer` suma
`practica_comision_id` requerido. La view resuelve el `pc` por id y valida:

- `pc.practica_id == ep.practica_id` → 400 si no.
- estudiante inscripto en `pc.comision` → 403 si no.

Desaparece el `.first()`. El `Intento` se crea con ese `pc`, igual que hoy.

`templates/ejercicios/ejercicio.html` manda `practica_comision_id: {{ pc.id }}`
en los tres cuerpos de `fetch` a `/api/intentos/` (líneas ~1279, ~1288, ~1297).

`docentes/views.py` — `_avanzar_progreso_por_aprobacion_docente` se reduce a
delegar con `intento.practica_comision`. Con la FK obligatoria se va el
fallback `secuencial = True` para intentos legacy.

## Read path

- `eps_resueltos(estudiante, pc)` filtra por `practica_comision=pc`.
- `esta_resuelto(estudiante, ep, pc)` suma `practica_comision=pc`.
- El subquery de último intento de `practica_detail` suma
  `practica_comision=pc`, para que el estado visible no cruce comisiones.
- `home()` y `ejercicio_detail` buscan `Progreso` por `practica_comision=pc`.
  Las dos vistas ya tienen el `pc` en mano (la URL del estudiante es
  `/practica/<pc_id>/ejercicio/<ep_id>/`).

`home()` hace hoy un `Progreso.objects.get()` por práctica dentro del loop de
comisiones. Como ya se está tocando esa consulta y los `pc` están todos
prefetcheados, pasa a un único queryset indexado por `practica_comision_id`.

## Consumidores

**`docentes/views.py`** — los dos prefetch
`practicas_comisiones__practica__progresos` pasan a
`practicas_comisiones__progresos` (líneas ~481 y ~657). Además de compilar,
dejan de traerse los `Progreso` de las otras comisiones que comparten la
práctica. En `_build_progreso_estudiantes`, `progresos_index` se arma por
`pc.id` en vez de `practica.id`, y `modo_por_practica` se simplifica porque ya
se está iterando sobre los `pc`.

**`analiticas/views.py`** — `completaron_map` agrupa por `practica_comision_id`
directo:

```python
completaron_map = {
    row['practica_comision_id']: row['n']
    for row in (Progreso.objects
                .filter(practica_comision_id__in=all_pc_ids,
                        ejercicio_practica_actual__isnull=True)
                .values('practica_comision_id')
                .annotate(n=Count('pk')))
}
```

El dict `pc_by_practica_comision` (línea 676) queda sin uso — su único consumo
es el remapeo de la línea 705 — y se elimina.

**`analiticas/research.py`** — el join
`practica__practicas_comisiones__comision_id__in=cids` pasa a
`practica_comision__comision_id__in=cids`.

Las dos consultas de analíticas hoy cuentan de más: un estudiante inscripto en
dos comisiones suma una práctica completada en cada una desde una sola fila.
Se corrige como efecto del cambio de clave.

**`mcp_intentos.py`** — `estadisticas_comision` cuenta `completaron` con el
mismo join (`practica__practicas_comisiones__comision_id`, línea ~618); pasa a
`practica_comision__comision_id`. El `.values('estudiante_id').distinct()` se
mantiene: deduplica entre prácticas, no entre comisiones, y un estudiante que
completa varias prácticas sigue teniendo una fila por cada una.

**Management commands** — `reconciliar_progreso_aprobaciones`,
`reevaluar_tablas_verdad`, `corregir_ejercicio_juicio` y
`reconciliar_V_mayuscula` agrupan por `(estudiante_id, practica_id)`; pasan a
`(estudiante_id, practica_comision_id)`, que ya sale del `Intento`.

**`ejercicios/admin.py`** — `ProgresoAdmin.list_display` usa
`practica_comision`; `list_filter` pasa de
`practica__practicas_comisiones__comision` a `practica_comision__comision`.

## Casos borde

**Estudiante en dos comisiones con la misma práctica.** Es el caso que el
cambio arregla: dos filas de `Progreso` independientes, cada una con el modo de
desbloqueo de su `PracticaComision`. Resolver en una no toca la otra.

**Intento legacy sin `practica_comision`.** No queda ninguno después de la
`0024`; la `0026` lo garantiza a nivel de esquema.

**Estudiante desinscripto con progreso.** La fila se borra en el backfill si no
queda ningún pc candidato. Sus intentos se atribuyen igual por la regla 2
mientras la práctica esté asignada a una sola comisión.

**Práctica desasignada de una comisión.** `PracticaComision` se borra y el
`Progreso` cae con él por `on_delete=CASCADE`. Antes sobrevivía huérfano
apuntando a la práctica. Es el comportamiento correcto: el progreso pertenece
al cursado, no a la práctica canónica.

**Práctica sin ejercicios.** Sin cambios.

## Tests

Los tests de caracterización que documentaban el comportamiento compartido no
existen (no hay `ProgresoCruzadoEntreComisionesTests`; lo más cercano es
`AvanceCruzadoEntreComisionesTests` en `docentes/tests.py`, que cubre
`_resueltos_por_estudiante_ep` y ya afirma el comportamiento correcto). Se
escriben ahora afirmando el comportamiento nuevo.

En `ejercicios/tests.py`:

- Dos comisiones que comparten práctica producen **dos** filas de `Progreso`.
- Un intento correcto en la comisión libre no mueve el puntero de la
  secuencial.
- `practica_detail` en la comisión B no muestra como resuelto un ejercicio
  resuelto en A.
- `ejercicio_detail` en B deja `puede_enviar=True` para un ejercicio ya
  resuelto en A.
- La API rechaza un `practica_comision_id` de otra práctica (400) y uno de una
  comisión donde el estudiante no está inscripto (403).
- La API rechaza el request sin `practica_comision_id` (400).
- Los tests existentes de `ProgresoModuloTests` y `DesbloqueoProgresivoTests`
  siguen pasando con la firma nueva.

Unitarios del backfill. No hay librería de testing de migraciones en
`requirements.txt` y no se agrega una: la lógica de atribución vive en
`ejercicios/backfill.py` como funciones puras que reciben las clases de modelo
por parámetro. La `0024` las llama con `apps.get_model(...)` y los tests con los
modelos reales, sin dependencia nueva y sin duplicar la regla.

- n=1 conserva el puntero verbatim.
- n=0 borra la fila.
- n≥2 abre en dos filas con punteros reconstruidos por separado.
- Backfill de `Intento`: regla 1 (inscripción única), regla 2 (desinscripto con
  práctica en una sola comisión), y que un caso genuinamente ambiguo queda en
  NULL.

## Riesgos

**El backfill de `Intento` es el paso peligroso, no el de `Progreso`.** Un
intento mal atribuido le saca a un estudiante un ejercicio ya resuelto, y con
`eps_resueltos` scopeado por comisión eso se traduce en re-bloqueo silencioso
en modo secuencial. Por eso las reglas de atribución exigen unicidad y no
adivinan.

**Scopear el read path sin backfillear `Intento` regresaría a estudiantes
reales.** Los dos cambios tienen que entrar juntos; el orden dentro de la
`0024` (intentos antes que progresos) es parte del diseño, no un detalle.

**La rama n≥2 no la ejercita ningún dato de producción.** Su cobertura es
puramente unitaria. Es aceptable porque es la rama que decide si el bug puede
volver, no la que arregla datos existentes.

**Si el supuesto de "sin estudiantes compartidos" no vale, falla el deploy.**
La `0026` no puede aplicar `null=False` con NULLs presentes, y la migración
aborta dentro de su transacción sin dejar el esquema a medias. Es el modo de
falla elegido a propósito: ruidoso en el deploy en vez de silencioso sobre un
estudiante.

**El PR queda apilado sobre #187.** No es mergeable hasta que #187 entre.
