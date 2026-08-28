# Task 4 — reporte

**Procedencia.** El subagente implementador se cortó por límite de sesión sin
commitear ni escribir reporte. El controller verificó el diff, encontró y
corrigió un defecto de seguridad, agregó dos tests y commiteó.

## Qué implementó el agente (verificado)

- `docentes/forms.py` — `CohorteForm` (ModelForm sobre `Cohorte`, campos `anio`
  y `cuatrimestre`) con `clean()` que rechaza duplicados con mensaje legible.
- `docentes/views.py` — `_siguiente_cohorte()` y `cohorte_create`, con gate
  `is_superuser` y desactivación de la anterior dentro de la misma transacción
  (necesario: el constraint `unica_cohorte_activa` rechaza dos activas).
- `docentes/urls.py` — ruta `cohortes/nueva/`.
- `docentes/tests.py` — `CohorteCreateTests` (5 tests).

Coincide con el brief. Suite `docentes` completa: 91 tests OK.

## Defecto encontrado por el controller: open redirect

`cohorte_create` hacía `destino = request.POST.get('next') or reverse(...)`,
usando un valor controlado por el cliente como destino de redirect sin
validarlo. Un POST con `next=https://evil.example.com/...` redirigía fuera del
sitio. El defecto venía del código de ejemplo del propio plan.

`docentes/views.py` ya tiene `_resolver_url_retorno(request)` (línea ~118), que
valida contra el host propio con `url_has_allowed_host_and_scheme` y devuelve
cadena vacía si no pasa. La vista ahora lo usa.

Tests agregados: `test_next_externo_no_redirige_fuera_del_sitio` y
`test_next_interno_se_respeta`.

## Comando y salida

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes.tests.CohorteCreateTests -v 2
Ran 7 tests in 61.126s
OK
```

## Riesgo para el review

El plan tiene el mismo patrón `request.POST.get('next')` en la Task 5 (el
parcial `_selector_cohorte.html` pasa `next` como hidden). Conviene verificar
que ninguna otra vista nueva repita el open redirect.
