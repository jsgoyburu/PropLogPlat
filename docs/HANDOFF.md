# Handoff — estado del repositorio al 2026-08-11

Documento de traspaso. Escrito por `claude-opus-5` para quien continúe, con el
estado real de las ramas, lo que quedó pendiente y las trampas del entorno.

Para el contexto del proyecto empezar por `AGENTS.md` y `MEMORY.md`. Este
documento cubre solo lo que está en vuelo ahora.

---

## 1. Lo que se hizo

Se agregó un modelo de **cohortes** (camadas de estudiantes: año + cuatrimestre)
para que una comisión pueda recibir camadas sucesivas conservando sus prácticas
y sin perder el historial de las anteriores.

Diseño en `docs/superpowers/specs/2026-08-09-modelo-cohorte-design.md`, plan en
`docs/superpowers/plans/2026-08-09-modelo-cohorte.md`, registro de trabajo en
`docs/bitacora/2026-08-cohortes/`.

**Antes de tocar cohortes, leer `docs/bitacora/2026-08-cohortes/README.md`.**
Tiene los cuatro invariantes que no hay que romper y el patrón de bug que
apareció doce veces.

---

## 2. Estado de las ramas

`master` contiene el modelo de cohortes completo (PR #189, mergeado en
`3505295`).

Quedan tres PRs abiertos de este trabajo, **independientes entre sí**, todos con
la suite en verde:

| PR | Rama | Qué hace | Nota |
|---|---|---|---|
| [#190](https://github.com/jsgoyburu/IPC-Logica/pull/190) | `claude/tests-hasher-rapido` | Hasher rápido en tests: 32 min → 12 s | **Mergear primero.** Dos commits, 20 líneas. Hace instantáneo todo lo que venga después. |
| [#191](https://github.com/jsgoyburu/IPC-Logica/pull/191) | `claude/selector-cohorte-home` | Selector de cohorte al home; filtro por camada en correcciones | Un commit sobre el merge de #189. |
| [#192](https://github.com/jsgoyburu/IPC-Logica/pull/192) | `claude/licencia-y-documentacion` | LICENSE AGPL-3.0 y documentación | Incluye este documento. |

**Los reviews automatizados de Codex sobre #189 y #190 están todos atendidos y
resueltos.** Los cinco de #189 y el de #190.

### PRs viejos, sin relación con este trabajo

Hay seis PRs abiertos de antes: #58, #79, #123, #126, #175 (todos de `codex/`) y
#178. No se revisaron en esta sesión y **pueden tener conflictos con `master`**
después del merge de #189, que tocó 43 archivos. Vale evaluarlos antes de
seguir acumulando.

---

## 3. Antes de desplegar a producción

Dos verificaciones que **no se pudieron hacer** desde el entorno de desarrollo,
porque requieren la base real:

**a) La guarda del backfill.** La migración `cursos/0009_backfill_cohorte`
aborta si encuentra inscripciones fuera de 2026, en vez de etiquetarlas mal en
silencio. Correr antes:

```bash
python manage.py shell -c "from cursos.models import Inscripcion; print(Inscripcion.objects.exclude(fecha_inscripcion__year=2026).count())"
```

Si no da `0`, la migración va a fallar a propósito. Hay que entender por qué
antes de forzar nada. Ojo además con `USE_TZ`: el filtro `__year` convierte a
`TIME_ZONE`, así que una inscripción del 31/12/2025 a las 23:00 ART cae en 2025.

**b) Permisos.** Crear una cohorte exige `is_superuser`, no `is_staff`. Quien
administre tiene que tener el primero o no va a poder abrir el cuatrimestre.

```bash
python manage.py shell -c "from accounts.models import Usuario; print(list(Usuario.objects.filter(is_staff=True).values('username','is_superuser')))"
```

**c) Ventana de mantenimiento.** `cursos/0010` y `ejercicios/0028` hacen
`ALTER TABLE ... SET NOT NULL` sobre `ejercicios_intento`, que es la tabla
grande. En PostgreSQL eso toma `ACCESS EXCLUSIVE` y escanea la tabla completa.

---

## 4. Antes de abrir el repositorio al público

La decisión de licencia ya está tomada: **AGPL-3.0** (ver `LICENSE` y la sección
de licencia del `README.md`). Falta:

1. **Escaneo de secretos sobre el historial completo.** Lo que se hizo fue un
   muestreo con `grep`: no hay base de datos ni fixtures commiteados, y lo único
   parecido a un `.env` en el historial es `.env.example`. Eso **no reemplaza** a
   `gitleaks` o `trufflehog` sobre todo el historial.
2. **Datos de estudiantes.** La plataforma maneja encuestas socioeducativas con
   consentimiento informado. El código es publicable; ningún dump, fixture o
   backup con datos reales debería entrar al repositorio, ni siquiera
   anonimizado sin analizar el riesgo de reidentificación.
3. **`CONTRIBUTING.md`** y código de conducta, si se espera contribución externa.

---

## 5. Trampas del entorno

- **El venv está en el directorio PADRE del repo:**
  `C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe`. El `.env` también.
- **`SECRET_KEY` no se carga solo.** Hay que exportarlo antes de correr tests.
- **`PYTHONIOENCODING=utf-8` es obligatorio en Windows.** Sin eso, la suite
  emite un `→` que revienta en cp1252 al redirigir la salida, y da errores
  espurios que no son del código. Costó una hora descubrirlo.

```bash
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test -v 1
```

- **Con #190 mergeado, la suite tarda ~12 segundos.** Sin #190, ~32 minutos.
- El repo tiene worktrees anidados en `.claude/worktrees/` que **contaminan los
  greps**. Usar `git grep` sobre archivos trackeados.

---

## 6. Deuda conocida

Ninguna bloquea, todas están registradas en `docs/bitacora/2026-08-cohortes/00-ledger.md`:

- El segundo test de `ProgresoDocenteRecursanteUsaCohorteActualTests` quedó casi
  tautológico: el `Prefetch` filtrado previene el escenario antes de que llegue a
  la función. El primer test de la clase sí lo cubre.
- `docentes/views.py` pasa `'cohorte_form': CohorteForm()` al contexto de
  `comision_detail` y ningún template lo usa.
- `CohorteForm.clean()` no suprime el `validate_unique()` automático, así que un
  duplicado muestra dos mensajes de error.
- El filtro de cohorte de `correccion_pendiente` defaultea a la camada activa.
  Eso oculta las correcciones pendientes de quien rinde un final hasta que se
  cambie el filtro. "Todas las camadas" es la primera opción del desplegable por
  esa razón. Si en uso real se pierden correcciones, invertir el default es una
  línea.

---

## 7. Una advertencia sobre el proceso

Las 12 tareas del plan se implementaron y revisaron **una por una**, cada una con
su review, y todas quedaron en verde. El review de la **rama completa** encontró
después 3 Critical y 9 Important. El review automatizado de Codex encontró 5 más
sobre eso.

Ninguno de esos 17 hallazgos era detectable mirando una tarea aislada: todos
cruzaban el sistema. Dos venían de decisiones del propio spec.

Si se sigue trabajando en cohortes por tareas chicas, **el review de rama
completa no es opcional**.
