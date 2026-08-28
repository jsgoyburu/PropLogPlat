# Task 12 — Reporte: Exponer cohortes en el MCP

## Resumen

- **Herramientas tocadas:** 26 funciones de `mcp_intentos.py` que envuelven `analiticas/research.py`
  (15 de la familia "encuesta" + 11 de la familia "intentos"), más 1 herramienta nueva (`listar_cohortes`).
- **Herramienta nueva:** `listar_cohortes()` agregada junto a `listar_comisiones` (antes de `listar_practicas`),
  con el código exacto del brief. También se agregó `listar_cohortes_compat` (wrapper `args/kwargs`) siguiendo
  el mismo patrón que `listar_comisiones_compat`, para no romper la promesa del docstring del módulo
  ("Todas las herramientas tienen un wrapper `*_compat`"); el brief no lo pedía explícitamente pero mantiene
  la consistencia con el resto de la API.
- Se actualizó el docstring del módulo (sección "Navegación") para listar `listar_cohortes`.

En cada una de las 26 funciones se agregó:
1. El parámetro `cohorte_ids: list[int] | None = None` **al final** de la firma (después de todos los
   parámetros existentes, incluidos los que tienen default).
2. La línea de docstring `cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.` dentro de `Args:`.
3. El pass-through `cohorte_ids=cohorte_ids` en la llamada a `_f(...)` (o al alias correspondiente,
   p. ej. `_correlaciones_encuesta`, `_red_errores`).

## Lista de las 26 funciones modificadas

Familia "encuesta" (15): `perfiles_encuesta_onboarding`, `distribucion_nse_onboarding`,
`distribucion_puntaje_logicas_onboarding`, `distribucion_pandemia_onboarding`,
`distribucion_facultad_onboarding`, `distribucion_carrera_onboarding`, `cohortes_onboarding`,
`cohortes_nse_onboarding`, `cohortes_pandemia_onboarding`, `desempeno_por_nse_onboarding`,
`desempeno_por_pandemia_onboarding`, `desempeno_por_puntaje_logicas`, `distribuciones_encuesta_detalle`,
`nube_ciencia`, `correlaciones_encuesta`.

Familia "intentos" (11): `tasa_entrada_efectiva`, `demora_primer_intento`, `persistencia_relativa`,
`intentos_hasta_correcto_sin_sesgo`, `desacople_docente_maquina`, `desacople_por_tipo`,
`tasa_abandono_local`, `indice_pared`, `errores_compartidos_semanticos`, `red_errores`,
`trabajo_vs_nota_logica`.

## Verificación de los wrappers `_compat`

Se leyó el bloque completo de wrappers `_compat` (líneas ~1569-1800 tras los cambios) para las 26
herramientas objetivo. Todos siguen la forma genérica:

```python
@mcp.tool()
async def X_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await X(**_compat_kwargs(args=args, kwargs=kwargs))
```

Ninguno de los 26 enumera parámetros a mano — todos reenvían `**_compat_kwargs(...)` tal cual, así que
heredan `cohorte_ids` automáticamente sin necesidad de editarlos. (Las excepciones que sí enumeran
parámetros a mano — `listar_comisiones_compat`, `obtener_ejercicio_compat`, `listar_intentos_compat`,
`obtener_intento_compat` — no pertenecen a la lista de 26 y no fueron tocadas.)

## Resultado del smoke test de firmas

Comando ejecutado (variante ampliada a las 26 funciones, no solo las 4 de ejemplo del brief):

```
$env:SECRET_KEY='x'; & '...\Scripts\python.exe' -c "..."
```

Salida:
```
total funciones a chequear: 26
faltan: ninguna
cohorte_ids no es el ultimo parametro en: ninguna
listar_cohortes params: []
```

Confirmado también:
- `import mcp_intentos` carga sin `SyntaxError` ni `ImportError` → `herramientas OK`.
- Invocación real de `listar_cohortes()` contra la base local (SQLite) devuelve una lista (`len: 1`),
  probando que el modelo `Cohorte` y el import `from cursos.models import Cohorte` funcionan.
- Invocación real de `distribucion_nse_onboarding(cohorte_ids=[1])` y
  `tasa_entrada_efectiva(cohorte_ids=[1])` — ambas ejecutan de punta a punta (MCP tool → `analiticas.research`)
  sin `TypeError` de binding de argumentos, confirmando que el pass-through funciona con la Task 11 ya
  aplicada.

## No se corrió la suite completa de Django

Por instrucción explícita de la tarea (el usuario hace de gate). Solo se corrieron los smoke tests de
carga de módulo y de firmas, más las tres invocaciones reales de arriba.

## Dudas / riesgos

- El brief no especificaba agregar `listar_cohortes_compat`; se agregó por consistencia con el resto del
  módulo (el docstring del archivo afirma que "todas las herramientas" tienen wrapper compat). Si no se
  quiere, es trivial de revertir (8 líneas).
- No se tocó `analiticas/research.py` (Task 11, ya mergeada) ni ningún modelo — el alcance se mantuvo
  estrictamente en `mcp_intentos.py`.
