Plan: docs/superpowers/plans/2026-08-09-modelo-cohorte.md (12 tareas)
Branch: claude/desbloqueo-configurable
Merge-base: 70b4722
Inicio: 20f3c2d

Task 1: complete (commits 20f3c2d..71e4391, review clean)
  Minor: imports de cursos/tests.py en medio del archivo, no en el bloque inicial
  Minor: CohorteAdmin sin docstring (patron ya mixto en cursos/admin.py)
Task 2: complete (commits 71e4391..a1fb998, review clean, 170 tests OK)
Task 3: complete (commits a1fb998..8817c80, review clean tras 2 rondas de fixes, 297 tests OK)
  Ejecutada por 3 subagentes (2 se cortaron sin commitear; controller verifico y commiteo)
  Review 1 hallo 2 Critical + 1 Important, todos corregidos en 60edc47
  Re-review hallo 1 Important mas (_build_progreso_estudiantes), corregido en 8817c80
  Call sites que el plan NO listaba: accounts/views.py, ejercicios/backfill.py,
    ejercicios/views.py (3 queries), 2 management commands, docentes/_build_progreso_estudiantes
  Nota para review final: analiticas/research.py:1019 cuenta practicas_completadas
    sin acotar por cohorte (preexistente, territorio Tasks 10-11)
  Entorno: manage.py test necesita PYTHONIOENCODING=utf-8 o da errores espurios
Task 4: complete (commits 8817c80..447e8ca, review clean, 7/7 CohorteCreateTests OK)
  Controller encontro y corrigio open redirect en cohorte_create (venia del codigo del plan)
  Minor: CohorteForm.clean() no suprime validate_unique() -> doble mensaje en duplicados
  Minor: IntegrityError por carrera exacta no atrapado -> 500 (la DB queda consistente)
  Informativo: _siguiente_cohorte usa month<=7; exportar_cohorte.py y research.py usan
    month<=6 (inconsistencia preexistente, la Task 10 la elimina)
  FUERA DE ALCANCE: 6 open redirects preexistentes en docentes/views.py
    (lineas ~1506, 1571, 1590, 2150, 2203, 2231) -> tarea aparte
Task 5: complete (commits 447e8ca..HEAD, review clean tras 1 fix, 101 tests docentes OK)
  Controller corrigio defecto de diseno del plan: _cohortes_de_comision ahora
    incluye siempre la cohorte activa (sin eso el selector y la pagina discrepaban
    y el primer alta de un cuatrimestre caia en la camada vieja)
  Review hallo 1 Important (aviso falso "cohorte cerrada" en paths de error) -> corregido
  Minor: cohorte_form muerto en el contexto (viene del plan)
  Minor: 2do test de ProgresoDocenteRecursante ya no cubre la colision de dict
    via la vista (el prefetch filtrado la previene antes); el 1ro si
Task 6: complete (commits c6db760..HEAD, review clean tras 1 fix, 109 tests docentes OK)
  Review hallo 2 Important (GET de parcial_create mostraba form; faltaba cobertura
    del ocultamiento en HTML) -> corregidos
  Controller encontro bug propio del plan: parcial_create pre-creaba NotaParcial
    para TODAS las camadas de la comision, no solo la del parcial
  Controller encontro comentario {# #} multilinea renderizandose visible desde Task 5
Task 7: complete (commits 60e4853..HEAD, review Approved, 323 tests suite completa OK)
  Implementador encontro 6 sitios de invalidacion de cache, mas que los del plan
    (docentes x3, ejercicios/api, 2 management commands); todos con clave de 2 partes
  Review hallo 1 Important: intentos_bulk_aprobar sin test -> agregado por controller
  Minor: defaults de _concentracion_practica/_velocidad_arranque quedaron 6/14
    (el brief decia 10/7); sin impacto, todo caller pasa kwarg explicito
  Minor: fallback cohorte.pk if cohorte else 0 deja entrada huerfana inofensiva
Task 8: complete (commit tras 6faa2ae, 94 tests ejercicios OK)
  Subagente se corto habiendo escrito solo los tests; controller implemento
  Controller adelanto cohorte_est antes del gate (se calculaba despues) y
    elimino las resoluciones duplicadas (una query extra por request)
  Controller agrego cobertura de ejercicio_detail: el gate esta duplicado en
    las dos vistas y solo se cubria practica_detail
Task 9: complete (commit tras 314ca6e, 112 tests docentes OK; hecha por controller, sin subagente)
Task 10: complete (commit 91e4139, 330 tests suite completa OK)
  Elimina las 4 derivaciones de cohorte por fecha (research, anonimizador,
    analiticas/views, exportar_cohorte) reemplazandolas por Inscripcion.cohorte
  Corrige ademas que exportar_cohorte no filtraba inscripciones por cohorte
  Queda 1 sola aparicion de corte por mes: docentes/views.py:604
    (_siguiente_cohorte, default del form cuando no hay cohorte activa) -> correcto
Task 11: complete (commit tras 91e4139, 90 tests analiticas OK)
  26 funciones publicas con cohorte_ids; verificado con parseo ast, no grep
  desagregar_por_comision correctamente sin el parametro (reenvia **kwargs)
Task 12: complete (commit f859a40, 333 tests suite completa OK)
  26 herramientas MCP con cohorte_ids (ultimo parametro) + listar_cohortes
  Verificado por el controller con inspect.signature en runtime
  Los wrappers _compat no necesitaron cambios (reenvian **kwargs)
TODAS LAS TAREAS COMPLETAS. Falta: review de rama entera + finishing-a-development-branch.

=== REVIEW FINAL DE RAMA (20f3c2d..f859a40, 17 commits) ===
VEREDICTO: NO listo para mergear. 3 Critical + 9 Important.

Patron unico de todas las fallas: donde la cohorte viaja como campo del modelo
esta bien; donde viaja como proxy (estudiante_ids) o donde el codigo asumia
"una inscripcion por (estudiante, comision)", esta mal. El cambio de
unique_together rompio un invariante del que otro codigo dependia y nadie
audito que dependia de el.

CRITICAL
C1 ejercicios/api/views.py:139-149 - el write path aplica estado_disponibilidad
   sin condicionar por cohorte: quien rinde final entra y ve el form, pero cada
   envio da 403. El caso de uso central esta roto.
C2 docentes/views.py:1085,1110 - estudiante_edit/remove usan get_object_or_404
   con inscripciones__comision: con dos inscripciones -> MultipleObjectsReturned
   -> HTTP 500 para cualquier recursante.
C3 docentes/views.py:1117 - la baja borra Inscripcion sin filtrar por cohorte:
   da de baja de C2 y borra tambien el registro de C1.

IMPORTANT
I1 docentes/views.py:255,288 - _aprobados/_resueltos_por_estudiante_ep sin cohorte
I2 analiticas/views.py (8 funciones) - estudiante_ids es mal proxy de cohorte;
   el test que debia cubrirlo usa dos estudiantes distintos, no un recursante
I3 docentes/views.py:495-528 - comisiones_list cuenta al recursante dos veces
I4 ejercicios/views.py:17-26 - home sin distinct(): comision duplicada
I5 docentes/views.py:1050 - estudiantes_exportar mezcla camadas
I6 reconciliar_V_mayuscula.py:135,198 + corregir_ejercicio_juicio.py:152 +
   recorregir_tabla_verdad.py:160 - Progreso .first() sin cohorte
I7 analiticas/anonimizador.py:330-360 - dataset de intentos ignora Intento.cohorte
I8 analiticas/views.py:768-780 + mcp_intentos.py:665 - doble conteo por join
I9 accounts/views.py:34-41 - el link publico re-inscribe a la camada activa

Migraciones: correctas. Dos salvedades operativas (guarda year=2026 sensible a
TZ; ALTER TABLE con ACCESS EXCLUSIVE sobre ejercicios_intento).
Minor diferidos: ninguno bloquea. research.py:1019 ya resuelto por Task 11.

FIX C1-C3: completo (commit tras 17b86db, 360 tests suite completa OK)
  Aplicado sobre HEAD post-merge (fea190a historial por cohorte + 17b86db open redirects)
  C1 test cubre tambien el caso complementario (la cohorte activa sigue bloqueada)
  C3: verificado que Progreso/Intento no cuelgan de Inscripcion -> historial intacto

=== HALLAZGOS DEL REVIEW FINAL: TODOS CERRADOS ===
C1-C3: 1ae0a1c (360 tests OK)
I9:    416cc2e (link publico ya no re-inscribe; solo accounts/)
I6-I7: 569b6d4 (produccion) + 3b314e5 (deuda de tests saldada, sin bugs nuevos)
I1-I5: f12c125 (368 tests OK)
I8:    2df5dc1
GATE FINAL COMBINADO: 381 tests OK, working tree limpio.

Nota: 569b6d4 estuvo en la rama sin cobertura hasta 3b314e5. Los tests
posteriores no revelaron bugs: el arreglo era correcto por lectura.
Caso no testeable documentado: practica_comision__isnull=True + filtro de
cohorte es inconstruible (migracion 0026 puso la columna NOT NULL).

PENDIENTE: decidir cierre de rama (merge / PR / dejar).

=== CERRADO ===
PR #189 abierto contra master: https://github.com/jsgoyburu/IPC-Logica/pull/189
Rama pusheada (332b412..3b314e5), viva para iterar sobre comentarios.
381 tests OK. 34 commits, 42 archivos, +7883/-667.

=== REVIEW AUTOMATIZADO CODEX EN PR #189 ===
4 bugs confirmados y arreglados en 98428d1 (387 tests OK, pusheado):
  - trabajo_vs_nota_logica elegia el primer parcial antes de filtrar cohorte
  - calcular_uso_plataforma_antes_parcial no acotaba Intento por cohorte
    (afectaba tambien a exportar_cohorte, llamador que Codex no marco)
  - exportar_cohorte aceptaba --cohorte-id y --parcial-id inconsistentes
  - demora_primer_intento duplicaba recursantes
Los 4 threads respondidos y resueltos.

PENDIENTE / DECISION DEL USUARIO: no existe forma de crear un recursante
desde la interfaz. estudiante_create y la importacion masiva crean cuentas
nuevas; ninguna adjunta una cuenta existente a una cohorte nueva. Solo se
puede desde el admin de Django o por ORM. Hace falta una pantalla de
re-inscripcion con confirmacion explicita. Thread 3752231160 dejado sin
resolver a proposito.

=== RE-INSCRIPCION (a34948c) ===
Cierra el 5to hallazgo de Codex. Decision del usuario: resolverlo en este PR.
Docente de la comision, solo cohorte activa. Select de recursantes (cuentas ya
visibles) + busqueda exacta username/email para pases (sin icontains: evita
tantear el padron). Pase confirma en 2 pasos. Reversible via estudiante_remove.
19 tests. Suite completa: 406 OK. Los 5 threads de Codex resueltos.

=== SELECTOR AL HOME (5e9665f) ===
Pedido del usuario: el boton y el selector de cohorte van al home, no a la
vista de comision (crear cohorte es global; tenerlo en una comision sugeria
alcance local). Cohorte pasa a sesion con ?cohorte= como override.
comisiones_list cuenta la camada seleccionada en vez de cohorte_activa()
hardcodeado. comision_detail muestra badge + link "cambiar".
Correcciones: filtro de cohorte, default a la activa, "Todas las camadas"
como primera opcion visible (necesaria para corregir finales).
Detalle no pedido y correcto: crear cohorte limpia la seleccion pinneada.
Suite completa: 416 tests OK. Pusheado al PR #189.
