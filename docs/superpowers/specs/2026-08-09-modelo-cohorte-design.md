# Modelo de cohorte

Agrega `Cohorte` como dimensión de las inscripciones, para que una comisión
reciba camadas sucesivas de estudiantes sin perder el historial de las
anteriores.

Base: rama `claude/desbloqueo-configurable`.

## Problema

Hoy no existe el concepto de cohorte. Cuando el módulo de investigación
necesita una, la deriva de `Inscripcion.fecha_inscripcion`:

```python
# analiticas/research.py:781
def _cohorte_de_fecha(fecha):
    cuatri = 1 if fecha.month <= 7 else 2
    return fecha.year, cuatri
```

Esa derivación es frágil —`fecha_inscripcion` es `auto_now_add`, así que no se
puede corregir desde el admin— pero el problema de fondo es otro: **no hay forma
de empezar un cuatrimestre nuevo en la misma comisión**. Las opciones actuales
son crear una comisión nueva (que queda desconectada de la anterior, y obliga a
reimportar todas las prácticas) o seguir agregando estudiantes a la existente
(que mezcla las camadas en todas las vistas y todas las analíticas).

Lo que se quiere: abrir el aula con la camada nueva y todo en cero, conservando
las mismas prácticas con los mismos ejercicios, y sin perder nada de lo anterior.

### Por qué no hace falta clonar

El primer diseño creaba una `Comision` por cuatrimestre y copiaba a ella las
`PracticaComision`. Es innecesario. **La `Comisión` ya es el aula**: porta las
prácticas, lxs docentes y la identidad. Lo único que se renueva es quién está
inscripto. Alcanza con etiquetar la inscripción y filtrar en las vistas.

Esto también evita duplicar filas de `PracticaComision` por cuatrimestre, que
además de redundante desincronizaría la configuración de prácticas entre
camadas.

## Modelo

```python
# cursos/models.py
class Cohorte(models.Model):
    anio = models.PositiveIntegerField()
    cuatrimestre = models.PositiveSmallIntegerField(choices=[(1, '1º'), (2, '2º')])
    activa = models.BooleanField(default=False)

    class Meta:
        unique_together = ['anio', 'cuatrimestre']
        ordering = ['-anio', '-cuatrimestre']
        constraints = [
            models.UniqueConstraint(
                fields=['activa'], condition=Q(activa=True),
                name='unica_cohorte_activa',
            ),
        ]
```

`Cohorte` es global, no por comisión: hay un solo cuatrimestre en curso en toda
la plataforma.

Cuatro FK nuevas, todas `PROTECT`:

| Modelo | Por qué necesita cohorte |
|---|---|
| `Inscripcion` | Es lo que segmenta a lxs estudiantes. La razón de ser del modelo. |
| `Progreso` | Sin esto, quien recursa reusa su fila y arranca con el progreso viejo hecho. |
| `Intento` | Sin esto, los intentos de la camada anterior contaminan las analíticas de la nueva. |
| `Parcial` | Las notas de un parcial pertenecen a una camada. |

`PROTECT` en las cuatro: borrar una cohorte con datos debe fallar ruidosamente.
Una cascada sobre cualquiera de estas tablas destruiría exactamente el historial
que este trabajo existe para preservar.

Y el cambio de constraint que habilita a lxs recursantes:

```python
# Progreso.Meta
unique_together = ['estudiante', 'practica_comision', 'cohorte']  # era sin cohorte
```

### Qué NO cambia

`Comision` no se toca. `PracticaComision` no se toca: `orden`,
`fecha_apertura`, `fecha_cierre` y `desbloqueo_secuencial` siguen siendo del
aula y compartidos entre cohortes. Lxs docentes siguen colgando de la comisión.

Las 977 referencias a `comision_id` en el código quedan intactas.

### Qué significa `activa`

Solo dos cosas: en qué cohorte abre el selector del panel, y a qué cohorte se
inscribe por defecto quien se da de alta.

**No controla acceso.** Estudiantes de camadas anteriores tienen que poder
seguir practicando —típicamente porque preparan un final— y lxs docentes tienen
que poder corregirles. `home` no filtra por cohorte.

## Atribución: qué cohorte se estampa

Cuando alguien registra un intento hoy, la cohorte que se le asigna es la de su
**inscripción más reciente en esa comisión**, ordenando por
`Inscripcion.fecha_inscripcion` descendente y desempatando por `id` descendente.

Una sola regla que resuelve los dos casos:

- Quien es de C1 y prepara el final sigue acumulando en C1, que es su camada.
- Quien recursa tiene inscripción en C2 y acumula ahí, arrancando de cero.

La cohorte es la **camada de pertenencia**, no el período del calendario. Un
intento hecho en septiembre por alguien de C1 pertenece a C1.

El punto de escritura es `IntentoCreateView`, que ya resuelve la
`PracticaComision` explícita desde el request (`ejercicios/api/views.py:115`),
así que la cohorte se deriva ahí y se pasa al `Intento.objects.create()` de la
línea 289. Lo mismo en el avance de `Progreso`, en `ejercicios/progreso.py`.

## Migración

Tres migraciones. **Toda la base actual es 2026-C1**: no hay estudiantes de otra
camada todavía, así que no hace falta derivar nada por fecha.

1. `cursos/00XX_cohorte` — crea el modelo.
2. FK nullable en `Inscripcion`, `Progreso`, `Intento`, `Parcial`.
3. Backfill + `NOT NULL` + constraint nuevo de `Progreso`, con `atomic = False`
   (PostgreSQL no permite `ALTER TABLE` en la misma transacción que INSERTs con
   FK deferred pendientes — mismo motivo que la 0015).

El backfill entero:

```python
fuera = Inscripcion.objects.exclude(fecha_inscripcion__year=2026).count()
if fuera:
    raise RuntimeError(f'{fuera} inscripciones fuera de 2026 — revisar antes de migrar')

cohorte = Cohorte.objects.create(anio=2026, cuatrimestre=1, activa=True)
for modelo in (Inscripcion, Progreso, Intento, Parcial):
    modelo.objects.filter(cohorte__isnull=True).update(cohorte=cohorte)
```

La guarda existe porque la migración corre contra producción sobre un supuesto
que no es verificable desde el repositorio. Si el supuesto vale no hace nada; si
no vale, aborta en vez de etiquetar mal en silencio.

Tras el `update`, verificar que no quede ninguna fila con `cohorte` nulo en las
cuatro tablas antes de aplicar el `NOT NULL`, y fallar si queda alguna.

## Vistas

### Panel docente

`comision_detail` acepta `?cohorte=<id>`, default la activa. Un id inexistente o
sin inscripciones en esa comisión cae a la activa en silencio.

Con la cohorte resuelta, el `Prefetch` de `inscripciones` filtra por ella y de
ahí sale `estudiantes_ids`. Como todas las secciones derivadas ya se construyen
desde esa lista —progreso, adaptaciones/CUD, estudiantes, y las ocho
analíticas— el filtrado se propaga solo.

`Parcial` filtra explícito por `(comision, cohorte)`.

Las secciones de **Prácticas** y **Docentes** no filtran por nada: son del aula.
Que la lista de prácticas no cambie al mover el selector es el requisito
central de este diseño.

**Selector** en el encabezado: las cohortes con al menos una inscripción en esta
comisión, más nuevas primero, la activa marcada. Oculto si hay una sola.

**Botón "Nueva cohorte"** → abre un form con `anio` y `cuatrimestre`,
precargados con el cuatrimestre siguiente al de la cohorte activa (si la activa
es 2026-C1, propone 2026-C2; si es C2, propone el año siguiente C1). El POST a
`cohorte_create` crea la `Cohorte` en una transacción, la marca activa y
desactiva la anterior. Si ya existe una cohorte con ese `(anio, cuatrimestre)`,
devuelve mensaje de error sin crearla ni cambiar cuál está activa.

No copia nada. Al volver, el aula muestra las mismas prácticas con los mismos
ejercicios y todas las secciones de estudiantes vacías.

#### Solo superusuarios

Crear una cohorte es una acción **global**: cambia cuál es la cohorte activa
para toda la plataforma, no solo para la comisión desde la que se dispara. Un
docente que abriera su cuatrimestre movería el piso de todas las demás
comisiones.

Por eso `cohorte_create` exige `request.user.is_superuser`. El botón se
renderiza solo para superusuarios y la vista POST rechaza al resto con 403.

Esto es una excepción deliberada al patrón del resto del panel, donde el gate
escalado es `is_staff` (`_require_docente`, `docentes/views.py:59`). La
consecuencia a tener presente: un docente con `is_staff=True` que no sea
superusuario tampoco puede crear cohortes. Es intencional —el criterio es
"quién puede mover la plataforma entera", no "quién administra"— pero conviene
verificar que lxs usuarixs que hoy administran cohortes tengan
`is_superuser=True` y no solo `is_staff=True`.

Al principio de cada cuatrimestre, entonces, el orden es: unx superusuarix crea
la cohorte, y recién después cada docente inscribe a su camada. Mientras la
cohorte no exista, el panel sigue parado en la anterior y las altas caen ahí.
El selector muestra siempre en qué cohorte se está parado, así que el estado es
visible antes de dar de alta a nadie.

El resto del panel no cambia de permisos: seleccionar cohortes anteriores,
inscribir, corregir y cargar notas siguen siendo del docente de la comisión.

### Qué se puede hacer en una cohorte no activa

| Acción | Estado |
|---|---|
| Alta individual de estudiante | Bloqueada |
| Importación masiva (.xlsx) | Bloqueada |
| Crear parcial | Bloqueada |
| Cargar/editar notas de parciales existentes | Disponible |
| Corregir intentos (`aprobado_docente`) | Disponible |
| Estudiantes practicando y avanzando | Disponible |

Una camada cerrada no crece ni suma instancias de evaluación, pero se le sigue
trabajando adentro.

Bloqueada significa que el formulario no se renderiza **y** que la vista POST
rechaza. Ocultar el form sin guardar el endpoint deja abierta la puerta a un
POST directo.

### Analíticas

Las ocho funciones de `analiticas/views.py` (`_ejercicios_mas_dificiles`,
`_estudiantes_en_riesgo`, `_distribucion_intentos`, `_evolucion_temporal`,
`_errores_sistematicos`, `_silencio_temprano`, `_concentracion_practica`,
`_velocidad_arranque`) pasan de `f(comision_ids, ...)` a
`f(comision_ids, estudiante_ids, ...)`.

Se pasa la lista de estudiantes y no el `cohorte_id` para que cada función no
tenga que hacer su propio join contra `Inscripcion`. `_silencio_temprano` ya la
necesita, porque incluye a quienes nunca intentaron.

La clave de caché pasa de `analiticas_{comision_id}` a
`analiticas_{comision_id}_{cohorte_id}`.

### Estudiante

`home` no cambia: quien tenga una inscripción ve el aula, sin importar su
camada.

El gate de fechas de `practica_detail` gana una condición: `fecha_apertura` y
`fecha_cierre` solo aplican a estudiantes de la cohorte activa. Quien es de una
camada anterior entra siempre.

Esto resuelve el efecto secundario de compartir las fechas entre cohortes: sin
la condición, ponerle fechas a las prácticas para la cursada nueva dejaría
afuera a quien prepara un final de la camada anterior.

### Corrección

Sin cambios funcionales. El conteo de pendientes ya cruza todas las cohortes
(`docentes/views.py:549` filtra solo por docente de la comisión). Se agrega un
badge de cohorte a cada fila para saber de qué camada es quien se está
corrigiendo.

## Tests

Sobre `docentes/tests.py` y `cursos/tests.py`, con el helper `_u()` que crea
usuarios con consentimientos completos para pasar el
`ForzarCambioPasswordMiddleware`.

**Migración** — que la guarda aborte si aparecen inscripciones fuera de 2026;
que tras el backfill no quede ninguna fila con `cohorte` nulo en las cuatro
tablas.

**Modelo** — que el nuevo `unique_together` acepte el mismo par
`(estudiante, practica_comision)` en dos cohortes y siga rechazando el duplicado
dentro de una; que `PROTECT` impida borrar una cohorte con datos; que no puedan
quedar dos cohortes activas.

**Panel docente** — que abra en la activa; que `?cohorte=` cambie la lista de
estudiantes; que **no** cambie la lista de prácticas; que los parciales sí
filtren; que dar de alta mirando una cohorte la inscriba en esa cohorte; que el
selector no aparezca con una sola cohorte; que los POST de alta, importación y
creación de parcial devuelvan error en cohortes no activas.

**Permisos de `cohorte_create`** — que un docente de la comisión reciba 403 en
el POST y no vea el botón; que un `is_staff=True, is_superuser=False` también
reciba 403 (es la distinción que este diseño introduce, y la que se rompe sola
si alguien "corrige" el check a `is_staff` por consistencia con el resto del
panel); que un superusuario pueda crearla; y que un POST rechazado no deje
cohorte creada ni cambie cuál está activa.

**Analíticas** — que las ocho devuelvan solo datos de la cohorte pedida, y que
el caché no se cruce entre cohortes. Esta última se rompe sola si alguien toca
la clave, y el síntoma es servir los números de una camada dentro de otra
durante cinco minutos.

**Estudiante** — que una camada vieja siga viendo el aula; que el gate de fechas
la deje pasar aunque la práctica esté cerrada; que sí frene a la cohorte activa.

**Recursante, end-to-end** — inscribir en C2 a alguien con historial en C1:
progreso arranca en cero, el de C1 queda intacto, los intentos nuevos se
estampan en C2.

**Errores** — crear una cohorte que ya existe da mensaje, no 500; un `?cohorte=`
inexistente cae a la activa; borrar una cohorte con datos falla con mensaje
legible en el admin.

## Punto abierto

Con la creación de parciales bloqueada en cohortes no activas, no hay dónde
asentar la nota de un final rendido por alguien de una camada anterior. Editar
notas de parciales existentes sí es posible. Si el final tiene que quedar
registrado en la plataforma, hace falta una decisión aparte —probablemente un
tipo de instancia distinto de `Parcial`, o permitir crear parciales marcados
como "final" en cohortes cerradas.

No bloquea la implementación de este diseño.
