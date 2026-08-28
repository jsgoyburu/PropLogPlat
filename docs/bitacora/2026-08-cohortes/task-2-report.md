# Task 2 Report: FK nullable en Inscripcion, Parcial, Progreso e Intento

## Archivos tocados

### Modificados
- `cursos/models.py` — Agregado campo `cohorte` FK a `Inscripcion` (línea ~148-154) y `Parcial` (línea ~178-184)
- `ejercicios/models.py` — Agregado campo `cohorte` FK a `Intento` (línea ~373-379) y `Progreso` (línea ~583-589)

### Migraciones generadas
- `cursos/migrations/0008_inscripcion_cohorte_parcial_cohorte.py` — Agrega campo `cohorte` a `Inscripcion` y `Parcial`
- `ejercicios/migrations/0027_intento_cohorte_progreso_cohorte.py` — Agrega campo `cohorte` a `Intento` y `Progreso`

## Detalles de implementación

### Especificaciones exactas aplicadas
Todos los campos se agregaron exactamente como especifica el brief:

**Inscripcion**
```python
cohorte = models.ForeignKey(
    'Cohorte',
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name='inscripciones',
    verbose_name='cohorte',
)
```

**Parcial**
```python
cohorte = models.ForeignKey(
    'Cohorte',
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name='parciales',
    verbose_name='cohorte',
)
```

**Intento**
```python
cohorte = models.ForeignKey(
    'cursos.Cohorte',
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name='intentos',
    verbose_name='cohorte',
)
```

**Progreso**
```python
cohorte = models.ForeignKey(
    'cursos.Cohorte',
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name='progresos',
    verbose_name='cohorte',
)
```

- Todos los FK usan `on_delete=models.PROTECT` (no CASCADE) para preservar historial.
- Todos son `null=True, blank=True` (nullable primero, como exige la tarea).
- Los `related_name` son respectivamente: `inscripciones`, `parciales`, `intentos`, `progresos`.
- En `cursos/models.py` se usa `'Cohorte'` (string sin app label) porque `Cohorte` vive en el mismo app.
- En `ejercicios/models.py` se usa `'cursos.Cohorte'` (string con app label) para evitar imports circulares.

### Migraciones
Ambas migraciones se generaron automáticamente por Django con `makemigrations cursos ejercicios`:

**cursos/migrations/0008_inscripcion_cohorte_parcial_cohorte.py**
- Depende de `cursos/0007_cohorte` (Task 1).
- Agrega dos campos AddField: `inscripcion.cohorte` e `parcial.cohorte`.

**ejercicios/migrations/0027_intento_cohorte_progreso_cohorte.py**
- Depende correctamente de `cursos/0008_inscripcion_cohorte_parcial_cohorte` (Task 2 de cursos) e `ejercicios/0026_intento_practica_comision_obligatoria` (anterior en ejercicios).
- Agrega dos campos AddField: `intento.cohorte` y `progreso.cohorte`.

## Pruebas

### Suite de tests ejecutada
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos ejercicios docentes -v 1
```

### Resultado
```
Ran 170 tests in 938.105s
OK
Destroying test database for alias 'default'...
```

**Conclusión:** Todos los tests pasaron sin regresiones. Los campos nullable y sin uso actual no afectaron ningún test existente.

### Tests de migraciones verificados también
Se probó específicamente que las migraciones corren correctamente:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos.tests.CohorteModelTests -v 1
```

Resultado:
```
Ran 5 tests in 0.010s
OK
```

## Commit realizado

Hash: `a1fb998`

Mensaje: `feat(cohorte): FK nullable en Inscripcion, Parcial, Progreso e Intento`

Cambios:
```
 4 files changed, 81 insertions(+)
 create mode 100644 cursos/migrations/0008_inscripcion_cohorte_parcial_cohorte.py
 create mode 100644 ejercicios/migrations/0027_intento_cohorte_progreso_cohorte.py
```

## Verificación de requisitos

- [x] **Step 1:** Campo `cohorte` agregado a `Inscripcion` con especificaciones exactas.
- [x] **Step 2:** Campo `cohorte` agregado a `Parcial` con especificaciones exactas.
- [x] **Step 3:** Campo `cohorte` agregado a `Intento` con especificaciones exactas.
- [x] **Step 4:** Campo `cohorte` agregado a `Progreso` con especificaciones exactas.
- [x] **Step 5:** Migraciones generadas automáticamente con names correctos (`0008_...` y `0027_...`).
- [x] **Step 6:** Suite completa verde: 170 tests OK en 938s.
- [x] **Step 7:** Commit realizado con mensaje exacto del brief.

## Notas y consideraciones

### Nullable primero (conforme a requisito)
Los campos son `null=True` en esta tarea. La Task 3 (posterior) hará el backfill y recién después aplicará `NOT NULL`. Esto es **obligatorio** para que las migraciones corran sobre bases que ya tienen datos históricos.

### No se tocó unique_together de Progreso
El brief especifica explícitamente que **no** se toque el `unique_together = ['estudiante', 'practica_comision']` de `Progreso` en esta tarea. Se respetó: el constraint nuevo irá en Task 3 después del backfill, cuando `cohorte` deje de ser nullable. Con filas actuales donde `cohorte=NULL`, aplicar un constraint que incluya `cohorte` haría fallar la migración.

### Migraciones interdependientes
La migración de `ejercicios` (0027) depende de la de `cursos` (0008), lo que es correcto Django puede aplicarlas en orden. Esto fue verificado en los tests y funcionó sin problemas.

### No hay secretos ni datos sensibles en las migraciones
Las migraciones solo contienen definiciones de campos, sin valores de datos.

## Conclusión

Task 2 completada exitosamente. Los cuatro modelos ahora tienen FK `cohorte` nullable, las migraciones fueron generadas y aplicadas correctamente, y la suite completa de tests sigue en verde. El código está listo para el backfill que hará Task 3.
