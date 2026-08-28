# Fix I9 — recursante involuntario en `acceso_comision`

## Qué cambié

`accounts/views.py`, vista `acceso_comision`, rama de usuario autenticado (no docente/staff):

Antes: siempre llamaba `Inscripcion.objects.get_or_create(estudiante=user, comision=comision, cohorte=cohorte)` con `cohorte = cohorte_activa()`. Como `unique_together` es `(estudiante, comision, cohorte)`, un estudiante con inscripción en una cohorte vieja no matcheaba y se le creaba una segunda inscripción en la cohorte activa — quedaba convertido en recursante sin haberlo pedido, con progreso en cero.

Después: primero se chequea si el estudiante ya tiene *alguna* inscripción en esa comisión (`Inscripcion.objects.filter(estudiante=user, comision=comision).exists()`, sin filtrar por cohorte). Si ya tiene una, no se crea nada y se redirige como siempre. Solo si no tiene ninguna se exige `cohorte_activa()` y se crea la inscripción en la cohorte activa.

## Decisión: rama anónima (registro)

La dejé sin tocar. En esa rama el usuario recién se crea con `form.save()` unas líneas antes de `get_or_create`, así que estructuralmente no puede tener una inscripción previa en ninguna comisión — el `get_or_create` ahí siempre inserta. Agregar el mismo chequeo sería código muerto. El test `test_registro_anonimo_sigue_creando_inscripcion` confirma que el flujo sigue funcionando igual.

## Decisión: guarda de `cohorte is None`

La moví adentro del `if not ya_inscripto`. Antes bloqueaba a *cualquier* estudiante logueado si no había cohorte activa, incluidos los que ya pertenecen a la comisión — eso los mandaba a un mensaje de error en vez de dejarlos entrar a algo a lo que ya tienen derecho. Ahora la guarda solo se evalúa cuando hace falta crear una inscripción nueva (estudiante sin inscripción previa en esa comisión), que es el único caso donde el `NOT NULL` de `Inscripcion.cohorte` puede reventar. Un estudiante ya inscripto pasa directo sin necesidad de cohorte activa, tal como pide el hallazgo.

El test `test_estudiante_logueado_sin_cohorte_activa_no_revienta_ni_inscribe` (clase preexistente `AccesoComisionSinCohorteActivaTests`) sigue pasando: cubre justamente el caso de un estudiante *sin* inscripción previa y sin cohorte activa, que debe seguir viendo el mensaje de error y no inscribirse.

## Tests agregados

Nueva clase `AccesoComisionRecursanteTests` en `accounts/tests.py`:

1. `test_estudiante_con_inscripcion_en_cohorte_no_activa_no_recibe_una_nueva`: estudiante con inscripción en cohorte 2025-C2 (no activa) abre el link de la comisión con 2026-C1 activa. Verifica que sigue teniendo exactamente 1 inscripción y que sigue siendo la de 2025-C2 (no se le tocó la cohorte).
2. `test_estudiante_sin_inscripcion_en_la_comision_recibe_una_en_cohorte_activa`: estudiante sin inscripción previa en la comisión abre el link. Verifica que se le crea 1 inscripción en la cohorte activa.
3. `test_registro_anonimo_sigue_creando_inscripcion`: flujo de registro anónimo (POST sin sesión) sigue creando usuario + inscripción en la cohorte activa.

Verifiqué que el test 1 falla por la razón correcta contra el código viejo (revertí temporalmente el fix en `accounts/views.py`, corrí los 3 tests nuevos, reapliqué el fix): falló con `AssertionError: 2 != 1` — exactamente la doble inscripción que describe el hallazgo. Los otros dos pasaban ya antes del fix (no ejercitan el bug), como se espera.

## Comando y salida

Comando (con el fix aplicado, corriendo la clase nueva + las dos clases relacionadas preexistentes de la misma vista para chequear que no rompí nada):

```
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test accounts.tests.AccesoComisionRecursanteTests accounts.tests.AccesoComisionTests accounts.tests.AccesoComisionSinCohorteActivaTests -v 1
```

Salida:

```
Creating test database for alias 'default'...
C:\Users\Angeles\Documents\IPC-Logica\Lib\site-packages\django\core\handlers\base.py:62: UserWarning: No directory at: C:\Users\Angeles\Documents\IPC-Logica\IPC-Logica\staticfiles\
  mw_instance = middleware(adapted_handler)
.........
----------------------------------------------------------------------
Ran 9 tests in 17.408s

OK
Destroying test database for alias 'default'...
Found 9 test(s).
  Intento: 0 atribuidos, 0 sin atribuir, 0 reatribuidos
  Progreso: 0 inequivocos, 0 huerfanos borrados, 0 ambiguos abiertos
System check identified no issues (0 silenced).
```

(La corrida previa contra el código sin arreglar, solo con la clase nueva, dio `FAILED (failures=1)` en el test 1 con `AssertionError: 2 != 1`, y los otros 2 tests en verde — confirmando que el test ejercita el bug real.)
