# Task 9 — reporte

Implementada por el controller sin subagente: son tres cambios chicos
(`select_related`, badge en el template, un test) y el arranque en frío de un
agente costaba más que el trabajo.

## Qué cambió

- `docentes/views.py` — `'cohorte'` agregado al `select_related` de
  `intentos_qs_paginados` en `correccion_pendiente`.
- `templates/docentes/correccion_pendiente.html` — badge con la cohorte del
  intento, junto al nombre de la comisión en cada fila.
- `docentes/tests.py` — `BadgeCohorteCorreccionTests`.

**Sin cambios funcionales.** `correccion_pendiente` ya cruzaba todas las
cohortes y así tiene que seguir: el caso de uso es corregirle a quien rinde un
final de una camada anterior. El badge solo hace visible de qué camada es cada
intento.

El test lo fija explícitamente: crea un intento de una cohorte **cerrada** y
verifica que aparece en el panel, además de que se ve su etiqueta. Si alguien
más adelante filtrara esta vista por cohorte activa, el test lo detecta.

## Comandos y salida

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes.tests.BadgeCohorteCorreccionTests -v 2
Ran 1 test in 4.568s
OK
```

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes -v 1
Ran 112 tests in 580.792s
OK
```
