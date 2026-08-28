# Task 8 — reporte

**Procedencia.** El subagente se cortó por límite de sesión habiendo escrito
solo la clase de tests, sin ningún cambio de producción. El controller
completó la implementación, agregó un test que faltaba y commiteó.

## Qué cambió

`ejercicios/views.py`, en `practica_detail` y `ejercicio_detail`:

```python
from cursos.cohortes import cohorte_de
cohorte_est = cohorte_de(usuario, pc.comision)
estado_disp = (
    pc.estado_disponibilidad()
    if cohorte_est is not None and cohorte_est.activa
    else 'abierta'
)
```

`'abierta'` es el literal que devuelve `estado_disponibilidad()` para el caso
disponible (`ejercicios/models.py:289`); los otros dos son `'no_iniciada'` y
`'cerrada'`. Un valor inventado saltearía las dos ramas siguientes y daría el
resultado correcto por la razón equivocada.

La condición exige `cohorte_est is not None` explícitamente: si por alguna ruta
el estudiante llegara sin inscripción, un `None` no debe habilitar el acceso.

## Dos cosas que agregué sobre lo que había el agente

1. **Adelanté la resolución de cohorte.** `cohorte_est` se calculaba *después*
   del gate en las dos vistas, así que condicionarlo requería moverlo antes. De
   paso saqué las resoluciones duplicadas que quedaban más abajo: eran una
   query extra por request.

2. **Cobertura de `ejercicio_detail`.** El gate está duplicado en las dos
   vistas y los tests solo cubrían `practica_detail`. Sin eso, alguien podía
   entrar a la práctica pero quedar afuera del ejercicio, que es donde
   realmente se practica.

## Que el test discrimina

`templates/ejercicios/practica_no_disponible.html:24` tiene
`<h2>Práctica cerrada</h2>`, así que el `assertNotContains(resp, 'Práctica
cerrada')` habría fallado antes del cambio: el gate se disparaba para la camada
vieja y renderizaba esa plantilla.

## Comandos y salida

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test ejercicios.tests.GateFechasPorCohorteTests -v 2
Ran 4 tests in 19.108s
OK
```

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test ejercicios -v 1
Ran 94 tests in 339.694s
OK
```

## Para el review

`home` no filtra por cohorte a propósito (hay un test que lo fija). Quien tiene
inscripción ve el aula, sea de la camada que sea; lo que cambia es qué progreso
se le muestra, que ya se resolvió en una tarea anterior.
