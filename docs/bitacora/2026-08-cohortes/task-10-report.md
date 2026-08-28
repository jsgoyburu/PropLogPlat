# Task 10: Unificar la noción de cohorte — Reporte

## Archivos tocados

- `analiticas/research.py`: eliminada `_cohorte_de_fecha`. `_registros_encuesta` ahora lee
  `inscripcion.cohorte.anio` / `.cuatrimestre`. `select_related` ampliado con `'cohorte'`.
  Docstring de la función actualizado para mencionar la fuente de la cohorte.
- `analiticas/anonimizador.py`: eliminada `_cohorte_de_fecha`. `dataset_encuesta` lee
  `insc.cohorte.anio/.cuatrimestre` y filtra por `cohorte__anio` / `cohorte__cuatrimestre`
  (antes por rango de meses de `fecha_inscripcion`). `select_related` de `dataset_encuesta`
  ampliado con `'cohorte'`. `dataset_intentos` filtra su queryset de inscripciones (usado solo
  para `.values()`, no accede a `insc.cohorte` como objeto) por `cohorte__anio`/`cohorte__cuatrimestre`
  — no necesitó `select_related` porque no instancia el objeto `Cohorte`.
- `analiticas/views.py`: `_cohortes_disponibles` reescrita para iterar `Cohorte.objects.filter(inscripciones__comision_id__in=...)`
  en vez de derivar de `fecha_inscripcion`.
- `cursos/management/commands/exportar_cohorte.py`: agregado `--cohorte-id`. La cohorte se
  resuelve como: explícita → la del parcial (`parcial.cohorte`) → `cohorte_activa()`; error claro si
  ninguna aplica. **Bug corregido**: las inscripciones ahora se filtran con `.filter(cohorte=cohorte)`
  — antes el CSV mezclaba todas las camadas de la comisión. Docstring del módulo actualizado.
- `analiticas/tests.py`: agregada `CohorteExplicitaTests` (Step 1 del brief) verificando que una
  inscripción tardía (noviembre) conserva la cohorte de su campo y no la que la regla vieja le
  hubiera asignado por fecha.

## Desvíos menores respecto al brief

- El Step 7 (agregar `cohorte=` a los `Inscripcion.objects.create` de `analiticas/tests.py`) ya
  estaba hecho por una tarea anterior — todas las instancias en el archivo ya pasaban `cohorte=`.
  No hubo nada que tocar ahí salvo el test nuevo.
- No existe un helper `_crear_encuesta(est)` en `analiticas/tests.py` como asumía el brief. El
  patrón real en el archivo es `EncuestaEstudiante.objects.create(estudiante=u, **campos)`
  (visto en `EncuestaOnboardingResearchTests` y en `CalcularNseTests._encuesta`). Solo
  `estudiante` es obligatorio en el modelo (el resto son `null=True`/`blank=True, default=''`),
  así que el test nuevo usa `EncuestaEstudiante.objects.create(estudiante=est)` directamente.
- El test usa el helper existente `_cohorte()` (ya presente en el archivo, línea 79) para obtener
  2026-C1 en vez de repetir `Cohorte.objects.get(anio=2026, cuatrimestre=1)` inline.

## Resultado del grep de verificación (Step 8)

```
git grep -n "_cohorte_de_fecha\|month <= 6\|month <= 7\|month__gte\|month__lte" -- '*.py'
```

```
docentes/views.py:604:        return hoy.year, (1 if hoy.month <= 7 else 2)
```

**Sí apareció una quinta coincidencia no listada en el brief.** Es `_siguiente_cohorte()` en
`docentes/views.py:593-607`. La analicé y decidí **no convertirla**, por lo siguiente:

- No deriva la cohorte de ningún registro existente (`Inscripcion`, `Parcial`, etc.) — no compite
  con leer `Inscripcion.cohorte` porque no hay ninguna inscripción involucrada.
- Es el fallback del formulario "crear cohorte" (`cohorte_create`) para proponer año/cuatrimestre
  por defecto cuando **no existe ninguna cohorte activa en toda la base** (arranque en frío del
  sistema). En ese escenario no hay ningún campo `Cohorte` que leer — es precisamente el caso que
  esta función existe para resolver.
- Fue introducida en una tarea distinta del mismo plan (`docs/superpowers/plans/2026-08-09-modelo-cohorte.md`,
  Step 4 de la sección de alta de cohortes), no en el inventario de derivaciones que esta tarea
  ataca.

Si se prefiere eliminar el `month <= 7` también ahí, la alternativa sería usar
`timezone.localdate().month` contra algún otro criterio, pero no hay un campo "correcto" que leer
en su lugar — seguiría siendo una heurística de fecha por diseño. Lo dejo señalado por si se
quiere revisar en otra tarea, pero no lo considero parte del bug que Task 10 ataca.

## Comando de test y salida

```
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.CohorteExplicitaTests analiticas.tests.EncuestaOnboardingResearchTests analiticas.tests.AnaliticasPorCohorteTests cursos.tests.ExportarCohorteTests -v 1
```

```
Creating test database for alias 'default'...
...............
----------------------------------------------------------------------
Ran 15 tests in 61.620s

OK
Destroying test database for alias 'default'...
```

También corrí el módulo completo `cursos.tests` (chico, cubre `exportar_cohorte` y el modelo
`Cohorte`) para asegurar que el filtro nuevo no rompe nada ahí:

```
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos.tests -v 1
```

```
Creating test database for alias 'default'...
.................
----------------------------------------------------------------------
Ran 17 tests in 29.327s

OK
```

No corrí la suite completa (`manage.py test` sin argumentos) por instrucción explícita del
orquestador — queda como gate suyo después del commit.

## select_related agregados

- `analiticas/research.py` — `_registros_encuesta`: `.select_related('estudiante', 'estudiante__encuesta', 'comision', 'cohorte')`.
- `analiticas/anonimizador.py` — `dataset_encuesta`: `.select_related('estudiante', 'estudiante__encuesta', 'comision', 'cohorte')`.
- `dataset_intentos` en `anonimizador.py` no necesitó `select_related('cohorte')`: su queryset de
  inscripciones se consume con `.values('estudiante_id', 'comision_id')`, nunca instancia
  `insc.cohorte`, así que no hay N+1 ahí.

## Dudas / riesgos

- El hallazgo de `docentes/views.py:604` (`_siguiente_cohorte`) queda documentado arriba; lo dejé
  sin tocar por juicio propio (no es una derivación competidora, es lógica de arranque en frío).
  Si el criterio del equipo es distinto, es un cambio de una línea y lo puedo hacer en una tarea
  separada.
- No hay tests dedicados a `dataset_encuesta`/`dataset_intentos` de `anonimizador.py` ni a
  `_cohortes_disponibles` en el repo (no los agregué: el brief no pedía cobertura nueva ahí, solo
  el reemplazo). Los cambios en esas funciones quedaron verificados por lectura de código y por
  los tests que sí tocan flujos relacionados (`ExportarCohorteTests`, `EncuestaOnboardingResearchTests`,
  `AnaliticasPorCohorteTests`), pero no por un test directo de esas dos funciones.
