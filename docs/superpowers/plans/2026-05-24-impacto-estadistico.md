# Impacto estadístico — Plan de implementación

> ## ⚠️ OBSOLETO — NO IMPLEMENTAR
>
> **Este plan ya fue ejecutado por completo.** Se archiva como registro histórico
> del diseño, no como trabajo pendiente. Las 39 casillas `- [ ]` de más abajo
> quedaron sin tildar en su momento; **no son tareas abiertas**.
>
> Evidencia de que está hecho, verificada el 2026-08-26 sobre `master`:
>
> | Lo que el plan pedía | Estado |
> |---|---|
> | `cursos/migrations/0004_notaparcial_ausente_logica_parcial_umbrales.py` | existe |
> | `calcular_nse`, `calcular_puntaje_logicas`, `calcular_desenlace_parcial`, `calcular_uso_plataforma_antes_parcial` | las cuatro en `analiticas/calculos.py` |
> | `cursos/management/commands/exportar_cohorte.py` | existe |
>
> **Además el modelo cambió después de este plan.** El campo que acá se llama
> `NotaParcial.puntaje_logica` hoy es `NotaParcial.nota_logica_parcial`: lo
> renombró `cursos/migrations/0005_rename_puntaje_logica_nota_logica_parcial.py`.
> El nombre viejo aparece 26 veces en este documento. Un agente que tomara esto
> como pendiente reintroduciría un campo y una migración ya superados.
>
> Para el estado real de esta funcionalidad, ver `MEMORY.md`.


> ~~**Para agentes:** REQUIRED SUB-SKILL: Usar `superpowers:subagent-driven-development` (recomendado) o `superpowers:executing-plans` para implementar este plan tarea por tarea.~~ **Anulado: ver el aviso de arriba.** Esta directiva se conserva tachada porque era parte del documento original, pero no debe seguirse.

**Goal:** Extender el modelo de parciales y agregar funciones analíticas para que los datos de la cohorte 2026-1 sean estadísticamente comparables con la serie histórica de la Memoria Profesional.

**Architecture:** Se agregan campos a `NotaParcial` y `Parcial` (cursos/models.py), se implementan funciones de cálculo en `analiticas/calculos.py` que replican exactamente la metodología del notebook de la Memoria, y se crea un management command `exportar_cohorte` que genera un CSV directamente apilable sobre el Excel histórico. La UI de carga de notas se actualiza para soportar el marcado explícito de ausentes.

**Tech Stack:** Django ORM, Python decimal/datetime, csv module estándar. Sin dependencias nuevas.

---

## Mapa de archivos

| Archivo | Acción | Responsabilidad |
|---------|--------|-----------------|
| `cursos/models.py` | Modificar | Agregar `ausente`, `puntaje_logica` a NotaParcial; `umbral_aprobacion`, `umbral_promocion` a Parcial |
| `cursos/migrations/0004_notaparcial_ausente_logica_parcial_umbrales.py` | Crear | Migración automática |
| `cursos/admin.py` | Modificar | Mostrar nuevos campos en inline |
| `cursos/management/__init__.py` | Crear | Paquete management |
| `cursos/management/commands/__init__.py` | Crear | Paquete commands |
| `cursos/management/commands/exportar_cohorte.py` | Crear | CSV exportación comparación histórica |
| `analiticas/calculos.py` | Modificar | Agregar `calcular_nse`, `calcular_puntaje_logicas`, `calcular_desenlace_parcial`, `calcular_uso_plataforma_antes_parcial` |
| `analiticas/tests.py` | Modificar | Tests para las 4 nuevas funciones |
| `cursos/tests.py` | Crear | Tests del management command |
| `docentes/forms.py` | Modificar | `get_nota_parcial_formset` incluye `ausente` y `puntaje_logica` |
| `docentes/views.py` | Modificar | `parcial_notas`: actualizar conteo de cargadas |
| `docentes/tests.py` | Modificar | Extender `ParcialTests` con casos de ausente |
| `templates/docentes/parcial_notas.html` | Modificar | Columna ausente, campo puntaje_logica, chip Ausente |

---

## Task 1: Campos de modelo y migración

**Files:**
- Modify: `cursos/models.py`
- Create: `cursos/migrations/0004_notaparcial_ausente_logica_parcial_umbrales.py` (auto)

- [ ] **Paso 1: Escribir el test fallido**

Agregar al final de `docentes/tests.py`, dentro de `class ParcialTests`:

```python
def test_notaparcial_tiene_campo_ausente_y_puntaje_logica(self):
    parcial = Parcial.objects.create(
        comision=self.comision, nombre='P1',
        fecha=datetime.date(2026, 6, 15), puntaje_total='10.00',
    )
    nota = NotaParcial.objects.create(parcial=parcial, estudiante=self.est1)
    self.assertFalse(nota.ausente)          # default False
    self.assertIsNone(nota.puntaje_logica)  # default null

def test_parcial_tiene_umbrales_con_defaults(self):
    parcial = Parcial.objects.create(
        comision=self.comision, nombre='P1',
        fecha=datetime.date(2026, 6, 15), puntaje_total='10.00',
    )
    from decimal import Decimal
    self.assertEqual(parcial.umbral_aprobacion, Decimal('4.00'))
    self.assertEqual(parcial.umbral_promocion, Decimal('7.00'))

def test_ausente_marca_correctamente(self):
    parcial = Parcial.objects.create(
        comision=self.comision, nombre='P1',
        fecha=datetime.date(2026, 6, 15), puntaje_total='10.00',
    )
    nota = NotaParcial.objects.create(parcial=parcial, estudiante=self.est1)
    nota.ausente = True
    nota.save()
    nota.refresh_from_db()
    self.assertTrue(nota.ausente)
    self.assertIsNone(nota.puntaje)
    self.assertIsNone(nota.puntaje_logica)
```

- [ ] **Paso 2: Verificar que el test falla**

```
cd C:\Users\Angeles\Documents\IPC-Logica\IPC-Logica
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test docentes.tests.ParcialTests.test_notaparcial_tiene_campo_ausente_y_puntaje_logica --verbosity=2
```

Esperado: `AttributeError: 'NotaParcial' object has no attribute 'ausente'`

- [ ] **Paso 3: Agregar campos a los modelos**

En `cursos/models.py`, dentro de `class NotaParcial`, después del campo `puntaje`:

```python
ausente = models.BooleanField(
    default=False,
    verbose_name='ausente al parcial',
    help_text='Marcar si el estudiante no se presentó. Cuando es True, puntaje y puntaje_logica deben ser null.',
)
puntaje_logica = models.DecimalField(
    max_digits=5,
    decimal_places=2,
    null=True,
    blank=True,
    verbose_name='puntaje parte lógica',
    help_text='Puntaje de la sección de lógica del parcial (subconjunto del puntaje global).',
)
```

En `cursos/models.py`, dentro de `class Parcial`, después del campo `puntaje_total`:

```python
umbral_aprobacion = models.DecimalField(
    max_digits=4,
    decimal_places=2,
    default=4.00,
    verbose_name='umbral aprobación (sobre 10)',
    help_text='Nota mínima normalizada (0-10) para aprobar. Default 4.00, igual que la serie histórica.',
)
umbral_promocion = models.DecimalField(
    max_digits=4,
    decimal_places=2,
    default=7.00,
    verbose_name='umbral promoción (sobre 10)',
    help_text='Nota mínima normalizada (0-10) para promocionar. Default 7.00, igual que la serie histórica.',
)
```

- [ ] **Paso 4: Generar la migración**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py makemigrations cursos --name notaparcial_ausente_logica_parcial_umbrales
```

Verificar que se creó `cursos/migrations/0004_notaparcial_ausente_logica_parcial_umbrales.py`.

- [ ] **Paso 5: Verificar que los tests pasan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test docentes.tests.ParcialTests.test_notaparcial_tiene_campo_ausente_y_puntaje_logica docentes.tests.ParcialTests.test_parcial_tiene_umbrales_con_defaults docentes.tests.ParcialTests.test_ausente_marca_correctamente --verbosity=2
```

Esperado: 3 tests PASS.

- [ ] **Paso 6: Commit**

```bash
git add cursos/models.py cursos/migrations/0004_notaparcial_ausente_logica_parcial_umbrales.py docentes/tests.py
git commit -m "feat(cursos): agregar ausente, puntaje_logica a NotaParcial y umbrales a Parcial"
```

---

## Task 2: Admin y formset

**Files:**
- Modify: `cursos/admin.py`
- Modify: `docentes/forms.py`

- [ ] **Paso 1: Actualizar admin inline**

En `cursos/admin.py`, en la clase `NotaParcialInline`, actualizar `fields` para incluir los nuevos campos:

```python
class NotaParcialInline(admin.TabularInline):
    model = NotaParcial
    extra = 0
    fields = ('estudiante', 'ausente', 'puntaje', 'puntaje_logica')
    readonly_fields = ('estudiante',)
```

- [ ] **Paso 2: Actualizar el formset**

En `docentes/forms.py`, reemplazar la función `get_nota_parcial_formset`:

```python
def get_nota_parcial_formset(extra=0):
    """Devuelve un FormSet class para editar puntajes de NotaParcial.

    Incluye ausente, puntaje (global) y puntaje_logica para permitir
    comparación estadística con la serie histórica.
    """
    from django.forms import modelformset_factory
    return modelformset_factory(
        NotaParcial,
        fields=['ausente', 'puntaje', 'puntaje_logica'],
        extra=extra,
        can_delete=False,
    )
```

- [ ] **Paso 3: Verificar que manage.py check pasa**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py check
```

Esperado: `System check identified no issues (0 silenced).`

- [ ] **Paso 4: Commit**

```bash
git add cursos/admin.py docentes/forms.py
git commit -m "feat(docentes): formset incluye ausente y puntaje_logica"
```

---

## Task 3: `calcular_nse` y `calcular_puntaje_logicas`

**Files:**
- Modify: `analiticas/calculos.py`
- Modify: `analiticas/tests.py`

Estas funciones replican **exactamente** la metodología del notebook `analisis.ipynb` de la Memoria Profesional, adaptando los nombres de columna del Excel a los nombres de campo del modelo `EncuestaEstudiante`.

- [ ] **Paso 1: Escribir los tests**

Agregar al final de `analiticas/tests.py`:

```python
# ── Imports necesarios para los nuevos tests ───────────────────────────────
# (agregar al bloque de imports existente al inicio del archivo si no están)
# from accounts.models import EncuestaEstudiante
# from django.contrib.auth import get_user_model
# Usuario = get_user_model()


class CalcularNseTests(TestCase):
    """Tests para calcular_nse(), réplica de puntaje_nse() de la Memoria."""

    def _encuesta(self, **kwargs):
        """Crea EncuestaEstudiante con campos por defecto neutros (puntaje=0)."""
        from accounts.models import EncuestaEstudiante
        from django.contrib.auth import get_user_model
        Usuario = get_user_model()
        u = Usuario.objects.create_user(username=f'nse_{id(kwargs)}', password='x')
        defaults = dict(
            con_quien_vive='familia_nuclear',  # 0
            dispositivos={'celular': 'individual', 'tablet': 'no_tengo',
                          'pc': 'no_tengo', 'laptop': 'no_tengo'},  # 0
            estudios_superiores='no',          # 0
            hizo_uba_xxi=False,                # 0
            tiempo_en_cbc='primero',           # 0
            materias_aprobadas=None,           # 0
            tiempo_viaje_puan='30_60',         # 0
            situacion_laboral='no_trabajo',
            dias_trabaja='no',                 # +1 (no trabaja + no busca)
            mudado_para_trabajar_estudiar=False,  # 0
            tiene_cud=False,                   # 0
        )
        defaults.update(kwargs)
        enc = EncuestaEstudiante.objects.create(estudiante=u, **defaults)
        return enc

    def test_puntaje_base_no_trabaja_no_busca(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta()
        puntaje, cat = calcular_nse(enc)
        self.assertEqual(puntaje, 1.0)    # solo item 7: no trabaja + no busca
        self.assertEqual(cat, 'Medio alto')

    def test_vivienda_solo_suma(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(con_quien_vive='solo')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 2.0)    # +1 vivienda + 1 laboral

    def test_vivienda_comparte_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(con_quien_vive='amigos')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 vivienda + 1 laboral

    def test_laptop_individual_suma(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(dispositivos={
            'celular': 'individual', 'laptop': 'individual',
            'tablet': 'no_tengo', 'pc': 'no_tengo',
        })
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 2.0)    # +1 laptop + 1 laboral

    def test_celular_compartido_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(dispositivos={
            'celular': 'compartido', 'laptop': 'no_tengo',
            'tablet': 'no_tengo', 'pc': 'no_tengo',
        })
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 celular + 1 laboral

    def test_viaje_menos_30_suma(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(tiempo_viaje_puan='menos_30')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 2.0)    # +1 viaje + 1 laboral

    def test_viaje_largo_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(tiempo_viaje_puan='mas_90')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 viaje + 1 laboral

    def test_cud_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(tiene_cud=True)
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 CUD + 1 laboral

    def test_migracion_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(mudado_para_trabajar_estudiar=True)
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 migración + 1 laboral

    def test_busca_trabajo_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(situacion_laboral='busco', dias_trabaja='no')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, -1.0)   # -1 laboral

    def test_categoria_bajo(self):
        from analiticas.calculos import calcular_nse
        # Forzar puntaje -2 -> Bajo
        enc = self._encuesta(
            con_quien_vive='amigos',       # -1
            situacion_laboral='busco',     # -1
            dias_trabaja='no',
            tiene_cud=True,               # -1
            mudado_para_trabajar_estudiar=True,  # -1
            tiempo_viaje_puan='mas_90',    # -1  → total -5 => Muy bajo
        )
        puntaje, cat = calcular_nse(enc)
        self.assertLess(puntaje, -2.5)
        self.assertEqual(cat, 'Muy bajo')

    def test_categoria_alto(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(
            con_quien_vive='solo',         # +1
            dispositivos={'celular': 'individual', 'laptop': 'individual',
                          'tablet': 'individual', 'pc': 'individual'},  # +3 (pc+laptop+tablet)
            tiempo_viaje_puan='menos_30',  # +1
            hizo_uba_xxi=True,            # +1
            estudios_superiores='si_uba',
            se_recibio_uba=True,          # +1
            tiempo_en_cbc='1_2_anios',
            materias_aprobadas=3,         # +1
        )
        puntaje, cat = calcular_nse(enc)
        self.assertGreaterEqual(puntaje, 2.5)
        self.assertEqual(cat, 'Alto')


class CalcularPuntajeLogicasTests(TestCase):
    """Tests para calcular_puntaje_logicas(), réplica del notebook."""

    def _encuesta(self, silo='', cirugia_ok=None, hilera=''):
        from accounts.models import EncuestaEstudiante
        from django.contrib.auth import get_user_model
        Usuario = get_user_model()
        u = Usuario.objects.create_user(username=f'log_{id((silo, cirugia_ok, hilera))}', password='x')
        return EncuestaEstudiante.objects.create(
            estudiante=u,
            acertijo_silogismo=silo,
            acertijo_cirugia_correcto=cirugia_ok,
            acertijo_hilera=hilera,
        )

    def test_cero_con_todo_incorrecto(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_alto', False, 'rivera')
        self.assertEqual(calcular_puntaje_logicas(enc), 0)

    def test_uno_solo_silogismo(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_bajo', False, 'rivera')
        self.assertEqual(calcular_puntaje_logicas(enc), 1)

    def test_uno_solo_cirugia(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_alto', True, 'rivera')
        self.assertEqual(calcular_puntaje_logicas(enc), 1)

    def test_uno_solo_hilera(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_alto', False, 'rodriguez')
        self.assertEqual(calcular_puntaje_logicas(enc), 1)

    def test_tres_con_todo_correcto(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_bajo', True, 'rodriguez')
        self.assertEqual(calcular_puntaje_logicas(enc), 3)

    def test_cirugia_none_no_suma(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_bajo', None, 'rodriguez')
        self.assertEqual(calcular_puntaje_logicas(enc), 2)  # silogismo + hilera

    def test_campos_vacios_dan_cero(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('', None, '')
        self.assertEqual(calcular_puntaje_logicas(enc), 0)
```

- [ ] **Paso 2: Verificar que los tests fallan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test analiticas.tests.CalcularNseTests analiticas.tests.CalcularPuntajeLogicasTests --verbosity=2 2>&1 | head -20
```

Esperado: `ImportError: cannot import name 'calcular_nse' from 'analiticas.calculos'`

- [ ] **Paso 3: Implementar las funciones**

Agregar al final de `analiticas/calculos.py` (antes de `_strip_html`):

```python
# ---------------------------------------------------------------------------
# Funciones de comparabilidad estadística con la serie histórica
# ---------------------------------------------------------------------------
# Replican exactamente la metodología del notebook analisis.ipynb de la
# Memoria Profesional (Goyburu 2026). Los nombres de campo corresponden a
# EncuestaEstudiante; los umbrales y categorías son idénticos al notebook.

def calcular_nse(encuesta) -> tuple:
    """Calcula el puntaje NSE y su categoría a partir de EncuestaEstudiante.

    Réplica exacta de puntaje_nse() del notebook analisis.ipynb.
    Devuelve (puntaje_float, categoria_str).
    Categorías: 'Muy bajo' / 'Bajo' / 'Medio bajo' / 'Medio alto' / 'Alto'.
    """
    puntaje = 0.0
    dispositivos = encuesta.dispositivos or {}

    # 1. Vivienda
    vivienda = encuesta.con_quien_vive or ''
    if vivienda == 'solo':
        puntaje += 1
    elif vivienda == 'amigos':
        puntaje -= 1
    # familia_nuclear, pareja, otros_familiares, residencia → 0

    # 2. Dispositivos
    for key in ('pc', 'laptop', 'tablet'):
        if dispositivos.get(key) == 'individual':
            puntaje += 1
    if dispositivos.get('celular') and dispositivos.get('celular') != 'individual':
        puntaje -= 1

    # 3. Estudios superiores previos con titulación
    if encuesta.estudios_superiores in ('si_uba', 'si_fuera_uba'):
        if encuesta.se_recibio_uba or encuesta.se_recibio_fuera_uba:
            puntaje += 1

    # 4. UBA XXI
    if encuesta.hizo_uba_xxi:
        puntaje += 1

    # 5. Trayectoria CBC: no primer cuatrimestre y ≥ 2 materias aprobadas
    if encuesta.tiempo_en_cbc != 'primero' and encuesta.tiempo_en_cbc != '':
        try:
            if encuesta.materias_aprobadas is not None and encuesta.materias_aprobadas >= 2:
                puntaje += 1
        except (TypeError, ValueError):
            pass

    # 6. Tiempo de viaje
    viaje = encuesta.tiempo_viaje_puan or ''
    if viaje == 'menos_30':
        puntaje += 1
    elif viaje in ('60_90', 'mas_90'):
        puntaje -= 1
    # 30_60 → 0

    # 7. Carga laboral combinada
    dias = encuesta.dias_trabaja or ''
    laboral = encuesta.situacion_laboral or ''
    if dias == 'no' and laboral == 'no_trabajo':
        puntaje += 1
    elif laboral == 'busco':
        puntaje -= 1
    elif dias == 'menos_5' and laboral == 'hasta_4':
        puntaje += 0.5
    elif dias == 'mas_5' and laboral == 'mas_6':
        puntaje -= 1

    # 8. Migración para trabajar/estudiar
    if encuesta.mudado_para_trabajar_estudiar:
        puntaje -= 1

    # 9. Discapacidad (CUD)
    if encuesta.tiene_cud:
        puntaje -= 1

    # Categorización (idéntica al notebook)
    if puntaje < -2.5:
        categoria = 'Muy bajo'
    elif puntaje < -1:
        categoria = 'Bajo'
    elif puntaje < 1:
        categoria = 'Medio bajo'
    elif puntaje < 2.5:
        categoria = 'Medio alto'
    else:
        categoria = 'Alto'

    return (puntaje, categoria)


def calcular_puntaje_logicas(encuesta) -> int:
    """Calcula el puntaje de acertijos lógicos (0–3) a partir de EncuestaEstudiante.

    Réplica exacta de puntaje_logicas() del notebook analisis.ipynb.
    Solo se cuentan los 3 acertijos incluidos en el análisis de la Memoria;
    el 4° acertijo (perros) no forma parte del puntaje por decisión de diseño.
    """
    puntaje = 0

    if encuesta.acertijo_silogismo == 'mas_bajo':
        puntaje += 1

    if encuesta.acertijo_cirugia_correcto is True:
        puntaje += 1

    if encuesta.acertijo_hilera == 'rodriguez':
        puntaje += 1

    return puntaje
```

- [ ] **Paso 4: Verificar que los tests pasan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test analiticas.tests.CalcularNseTests analiticas.tests.CalcularPuntajeLogicasTests --verbosity=2
```

Esperado: todos los tests PASS.

- [ ] **Paso 5: Commit**

```bash
git add analiticas/calculos.py analiticas/tests.py
git commit -m "feat(analiticas): calcular_nse y calcular_puntaje_logicas (réplica Memoria)"
```

---

## Task 4: `calcular_desenlace_parcial`

**Files:**
- Modify: `analiticas/calculos.py`
- Modify: `analiticas/tests.py`

- [ ] **Paso 1: Escribir los tests**

Agregar al final de `analiticas/tests.py`:

```python
class CalcularDesenlaceParcialTests(TestCase):
    """Tests para calcular_desenlace_parcial(), réplica de pd.cut del notebook."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from cursos.models import Comision, Parcial, NotaParcial, Inscripcion
        Usuario = get_user_model()
        import datetime
        from decimal import Decimal
        docente = Usuario.objects.create_user('doc_desp', password='x', es_docente=True)
        comision = Comision.objects.create(nombre='C1')
        comision.docentes.add(docente)
        self.est = Usuario.objects.create_user('est_desp', password='x')
        self.parcial = Parcial.objects.create(
            comision=comision, nombre='P1',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('10.00'),
            umbral_aprobacion=Decimal('4.00'),
            umbral_promocion=Decimal('7.00'),
        )
        self.NotaParcial = NotaParcial

    def _nota(self, puntaje=None, ausente=False):
        n = self.NotaParcial.objects.create(
            parcial=self.parcial,
            estudiante=self.est,
            puntaje=puntaje,
            ausente=ausente,
        )
        return n

    def test_ausente_devuelve_ausente(self):
        from analiticas.calculos import calcular_desenlace_parcial
        nota = self._nota(ausente=True)
        self.assertEqual(calcular_desenlace_parcial(nota), 'Ausente')

    def test_puntaje_none_devuelve_none(self):
        from analiticas.calculos import calcular_desenlace_parcial
        nota = self._nota(puntaje=None)
        self.assertIsNone(calcular_desenlace_parcial(nota))

    def test_nota_cero_es_aplazo(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('0'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Aplazo')

    def test_nota_3_es_aplazo(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('3.00'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Aplazo')

    def test_nota_4_es_final(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('4.00'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Final')

    def test_nota_6_es_final(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('6.99'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Final')

    def test_nota_7_es_promocion(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('7.00'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Promoción')

    def test_nota_10_es_promocion(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('10.00'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Promoción')

    def test_normaliza_escala_puntaje_total_20(self):
        """Puntaje 14/20 → normalizado 7.0 → Promoción."""
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        from cursos.models import Parcial, Comision
        import datetime
        comision = Comision.objects.create(nombre='C2')
        parcial20 = Parcial.objects.create(
            comision=comision, nombre='P2',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('20.00'),
        )
        nota = self.NotaParcial.objects.create(
            parcial=parcial20, estudiante=self.est,
            puntaje=Decimal('14.00'),
        )
        self.assertEqual(calcular_desenlace_parcial(nota), 'Promoción')

    def test_umbral_personalizado(self):
        """Umbral de aprobación 5 → nota 4.5 es Aplazo."""
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        from cursos.models import Parcial, Comision
        import datetime
        comision = Comision.objects.create(nombre='C3')
        p = Parcial.objects.create(
            comision=comision, nombre='P3',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('10.00'),
            umbral_aprobacion=Decimal('5.00'),
            umbral_promocion=Decimal('8.00'),
        )
        nota = self.NotaParcial.objects.create(
            parcial=p, estudiante=self.est, puntaje=Decimal('4.50'),
        )
        self.assertEqual(calcular_desenlace_parcial(nota), 'Aplazo')
```

- [ ] **Paso 2: Verificar que los tests fallan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test analiticas.tests.CalcularDesenlaceParcialTests --verbosity=2 2>&1 | head -10
```

Esperado: `ImportError: cannot import name 'calcular_desenlace_parcial'`

- [ ] **Paso 3: Implementar la función**

Agregar en `analiticas/calculos.py`, justo después de `calcular_puntaje_logicas`:

```python
def calcular_desenlace_parcial(nota_parcial) -> str | None:
    """Categoriza el desenlace de un NotaParcial en Ausente/Aplazo/Final/Promoción.

    Réplica de pd.cut(..., bins=[0,1,4,7,10]) del notebook analisis.ipynb.
    Normaliza el puntaje a escala 0–10 usando parcial.puntaje_total.

    Returns:
        'Ausente' | 'Aplazo' | 'Final' | 'Promoción' | None (si pendiente)
    """
    if nota_parcial.ausente:
        return 'Ausente'

    if nota_parcial.puntaje is None:
        return None

    parcial = nota_parcial.parcial
    # Normalizar a escala 0–10
    nota_norm = (nota_parcial.puntaje / parcial.puntaje_total) * 10

    if nota_norm < parcial.umbral_aprobacion:
        return 'Aplazo'
    elif nota_norm < parcial.umbral_promocion:
        return 'Final'
    else:
        return 'Promoción'
```

- [ ] **Paso 4: Verificar que los tests pasan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test analiticas.tests.CalcularDesenlaceParcialTests --verbosity=2
```

Esperado: todos PASS.

- [ ] **Paso 5: Commit**

```bash
git add analiticas/calculos.py analiticas/tests.py
git commit -m "feat(analiticas): calcular_desenlace_parcial (réplica bins del notebook)"
```

---

## Task 5: `calcular_uso_plataforma_antes_parcial`

**Files:**
- Modify: `analiticas/calculos.py`
- Modify: `analiticas/tests.py`

Esta función computa ~20 indicadores de uso de la plataforma por estudiante antes de la fecha del parcial.

- [ ] **Paso 1: Escribir los tests**

Agregar al final de `analiticas/tests.py`:

```python
class CalcularUsoPlataformaTests(TestCase):
    """Tests para calcular_uso_plataforma_antes_parcial()."""

    def setUp(self):
        import datetime
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from cursos.models import Comision, Parcial, Inscripcion
        from ejercicios.models import Ejercicio, Practica, EjercicioPractica, PracticaComision, Intento
        from django.utils import timezone

        Usuario = get_user_model()
        self.est = Usuario.objects.create_user('uso_est', password='x')
        self.docente = Usuario.objects.create_user('uso_doc', password='x', es_docente=True)
        self.comision = Comision.objects.create(nombre='C-uso')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision)

        self.parcial = Parcial.objects.create(
            comision=self.comision, nombre='P1',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('10.00'),
        )

        # Ejercicio y práctica
        self.ejercicio = Ejercicio.objects.create(
            titulo='E1',
            enunciado='p → q',
            formula_solucion='p → q',
            tipo='formalizacion',
            creado_por=self.docente,
        )
        self.practica = Practica.objects.create(
            titulo='P', creada_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=self.practica, ejercicio=self.ejercicio, orden=1,
        )
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )

        # Fecha antes del parcial
        self.antes = timezone.make_aware(
            datetime.datetime(2026, 6, 10, 12, 0)
        )
        # Fecha después del parcial
        self.despues = timezone.make_aware(
            datetime.datetime(2026, 6, 16, 12, 0)
        )

    def _intento(self, correcto=True, cuando=None, categoria=None):
        from ejercicios.models import Intento
        from django.utils import timezone
        cuando = cuando or self.antes
        i = Intento.objects.create(
            estudiante=self.est,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            respuesta_raw='p → q',
            es_correcto=correcto,
            error_categoria=categoria,
        )
        # Forzar timestamp (auto_now_add no permite override directo)
        Intento.objects.filter(pk=i.pk).update(timestamp=cuando)
        i.refresh_from_db()
        return i

    def test_sin_intentos_devuelve_ceros(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['intentos_totales'], 0)
        self.assertEqual(resultado['ejercicios_distintos'], 0)
        self.assertEqual(resultado['ejercicios_resueltos'], 0)
        self.assertIsNone(resultado['tasa_exito'])
        self.assertEqual(resultado['dias_activos'], 0)

    def test_intento_posterior_no_cuenta(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        self._intento(correcto=True, cuando=self.despues)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['intentos_totales'], 0)

    def test_intento_correcto_cuenta(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        self._intento(correcto=True)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['intentos_totales'], 1)
        self.assertEqual(resultado['ejercicios_resueltos'], 1)
        self.assertEqual(resultado['tasa_exito'], 1.0)

    def test_intento_incorrecto_baja_tasa(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        import datetime
        from django.utils import timezone
        t1 = timezone.make_aware(datetime.datetime(2026, 6, 10, 10, 0))
        t2 = timezone.make_aware(datetime.datetime(2026, 6, 10, 11, 0))
        self._intento(correcto=False, cuando=t1, categoria='polaridad')
        self._intento(correcto=True, cuando=t2)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['intentos_totales'], 2)
        self.assertAlmostEqual(resultado['tasa_exito'], 0.5)
        self.assertEqual(resultado['err_polaridad'], 1)

    def test_dias_activos(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        import datetime
        from django.utils import timezone
        d1 = timezone.make_aware(datetime.datetime(2026, 6, 5, 9, 0))
        d2 = timezone.make_aware(datetime.datetime(2026, 6, 7, 9, 0))
        self._intento(cuando=d1)
        self._intento(cuando=d2)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['dias_activos'], 2)

    def test_dias_primer_y_ultimo_uso(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        import datetime
        from django.utils import timezone
        d1 = timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0))
        d2 = timezone.make_aware(datetime.datetime(2026, 6, 10, 9, 0))
        self._intento(cuando=d1)
        self._intento(cuando=d2)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['dias_primer_uso_hasta_1p'], 14)  # 15 - 1
        self.assertEqual(resultado['dias_ultimo_uso_hasta_1p'], 5)   # 15 - 10

    def test_categorias_error_en_resultado(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        self._intento(correcto=False, categoria='tautologia')
        self._intento(correcto=False, categoria='tautologia')
        self._intento(correcto=False, categoria='polaridad')
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['err_tautologia'], 2)
        self.assertEqual(resultado['err_polaridad'], 1)
        self.assertEqual(resultado['err_contradiccion'], 0)
```

- [ ] **Paso 2: Verificar que los tests fallan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test analiticas.tests.CalcularUsoPlataformaTests --verbosity=2 2>&1 | head -10
```

Esperado: `ImportError: cannot import name 'calcular_uso_plataforma_antes_parcial'`

- [ ] **Paso 3: Implementar la función**

Agregar en `analiticas/calculos.py`, después de `calcular_desenlace_parcial`:

```python
_ERROR_CATEGORIAS_IMPACTO = [
    'tautologia', 'contradiccion', 'polaridad', 'mas_fuerte', 'mas_debil',
    'equivalente_alt', 'error_parcial_1', 'error_parcial_2', 'error_sistemico',
    'variables_extra', 'variables_menos',
]


def calcular_uso_plataforma_antes_parcial(estudiante, parcial) -> dict:
    """Indicadores de uso de la plataforma para un estudiante antes del 1er parcial.

    Filtra Intento del estudiante en la comisión del parcial con timestamp
    anterior a parcial.fecha. Devuelve ~20 indicadores agrupados en:
    - Volumen: intentos_totales, ejercicios_distintos, practicas_abiertas
    - Calidad: ejercicios_resueltos, tasa_exito, promedio_intentos_hasta_correcto
    - Temporal: dias_activos, dias_primer_uso_hasta_1p, dias_ultimo_uso_hasta_1p
    - Errores: err_<categoria> para las 11 categorías del clasificador
    """
    import datetime as _dt
    from django.db.models import Count, Min, Max
    from ejercicios.models import Intento

    fecha_corte = _dt.datetime.combine(parcial.fecha, _dt.time.min)

    qs = Intento.objects.filter(
        estudiante=estudiante,
        practica_comision__comision=parcial.comision,
        timestamp__lt=fecha_corte,
    )

    total = qs.count()

    resultado = {
        'intentos_totales': total,
        'ejercicios_distintos': 0,
        'practicas_abiertas': 0,
        'ejercicios_resueltos': 0,
        'tasa_exito': None,
        'promedio_intentos_hasta_correcto': None,
        'dias_activos': 0,
        'dias_primer_uso_hasta_1p': None,
        'dias_ultimo_uso_hasta_1p': None,
    }
    for cat in _ERROR_CATEGORIAS_IMPACTO:
        resultado[f'err_{cat}'] = 0

    if total == 0:
        return resultado

    # Volumen
    resultado['ejercicios_distintos'] = (
        qs.values('ejercicio_practica__ejercicio').distinct().count()
    )
    resultado['practicas_abiertas'] = (
        qs.values('practica_comision').distinct().count()
    )

    # Calidad
    correctos = qs.filter(es_correcto=True)
    n_correctos = correctos.count()
    resultado['tasa_exito'] = n_correctos / total

    # Ejercicios resueltos (al menos un intento correcto)
    resueltos_ids = set(
        correctos.values_list('ejercicio_practica__ejercicio', flat=True).distinct()
    )
    resultado['ejercicios_resueltos'] = len(resueltos_ids)

    # Promedio de intentos hasta el primer acierto (solo ejercicios resueltos)
    if resueltos_ids:
        sumas = []
        for ej_id in resueltos_ids:
            intentos_ej = list(
                qs.filter(ejercicio_practica__ejercicio=ej_id)
                .order_by('timestamp')
                .values_list('es_correcto', flat=True)
            )
            # Contar intentos hasta el primero correcto (inclusive)
            for idx, ok in enumerate(intentos_ej, start=1):
                if ok:
                    sumas.append(idx)
                    break
        if sumas:
            resultado['promedio_intentos_hasta_correcto'] = sum(sumas) / len(sumas)

    # Temporal
    fechas = qs.values_list('timestamp__date', flat=True).distinct()
    dias_distintos = list(fechas)
    resultado['dias_activos'] = len(dias_distintos)

    agg = qs.aggregate(primero=Min('timestamp'), ultimo=Max('timestamp'))
    if agg['primero']:
        resultado['dias_primer_uso_hasta_1p'] = (
            parcial.fecha - agg['primero'].date()
        ).days
    if agg['ultimo']:
        resultado['dias_ultimo_uso_hasta_1p'] = (
            parcial.fecha - agg['ultimo'].date()
        ).days

    # Perfil de errores (solo intentos incorrectos con categoría clasificada)
    incorrectos_cat = (
        qs.filter(es_correcto=False, error_categoria__isnull=False)
        .values('error_categoria')
        .annotate(n=Count('id'))
    )
    for row in incorrectos_cat:
        cat = row['error_categoria']
        if f'err_{cat}' in resultado:
            resultado[f'err_{cat}'] = row['n']

    return resultado
```

- [ ] **Paso 4: Verificar que los tests pasan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test analiticas.tests.CalcularUsoPlataformaTests --verbosity=2
```

Esperado: todos PASS.

- [ ] **Paso 5: Commit**

```bash
git add analiticas/calculos.py analiticas/tests.py
git commit -m "feat(analiticas): calcular_uso_plataforma_antes_parcial (~20 indicadores)"
```

---

## Task 6: Management command `exportar_cohorte`

**Files:**
- Create: `cursos/management/__init__.py`
- Create: `cursos/management/commands/__init__.py`
- Create: `cursos/management/commands/exportar_cohorte.py`
- Create: `cursos/tests.py`

- [ ] **Paso 1: Crear la estructura de directorios**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe -c "
import os
os.makedirs('cursos/management/commands', exist_ok=True)
open('cursos/management/__init__.py', 'w').close()
open('cursos/management/commands/__init__.py', 'w').close()
print('Directorios creados')
"
```

- [ ] **Paso 2: Escribir los tests**

Crear `cursos/tests.py`:

```python
"""Tests del management command exportar_cohorte."""
import csv
import datetime
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from cursos.models import Comision, Inscripcion, Parcial, NotaParcial

Usuario = get_user_model()


def _u(username, **kwargs):
    user = Usuario.objects.create_user(username=username, password='x', **kwargs)
    Usuario.objects.filter(pk=user.pk).update(
        consentimiento_pedagogico=True,
        consentimiento_investigacion=True,
        encuesta_completada=True,
    )
    user.refresh_from_db()
    return user


class ExportarCohorteTests(TestCase):

    def setUp(self):
        self.docente = _u('exp_doc', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC 2026-1')
        self.comision.docentes.add(self.docente)
        self.est1 = _u('exp_est1')
        self.est2 = _u('exp_est2')
        Inscripcion.objects.create(estudiante=self.est1, comision=self.comision)
        Inscripcion.objects.create(estudiante=self.est2, comision=self.comision)
        self.parcial = Parcial.objects.create(
            comision=self.comision,
            nombre='1er Parcial',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('10.00'),
        )

    def _call_command(self, comision_id, parcial_id=None):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        args = [str(comision_id)]
        if parcial_id:
            args += ['--parcial-id', str(parcial_id)]
        call_command('exportar_cohorte', *args, stdout=out)
        out.seek(0)
        return list(csv.DictReader(out))

    def test_exporta_una_fila_por_estudiante(self):
        rows = self._call_command(self.comision.id)
        self.assertEqual(len(rows), 2)

    def test_encabezados_presentes(self):
        rows = self._call_command(self.comision.id)
        expected_headers = [
            'id_anon', 'facultad', 'carrera', 'puntaje_logicas', 'categoria_nse',
            'ausente_1p', 'nota_global_1p', 'desenlace_1p',
            'intentos_totales', 'tasa_exito',
            'err_tautologia', 'err_polaridad',
        ]
        for h in expected_headers:
            self.assertIn(h, rows[0], f'Falta columna: {h}')

    def test_sin_parcial_desenlace_vacio(self):
        rows = self._call_command(self.comision.id, self.parcial.id)
        for row in rows:
            self.assertEqual(row['ausente_1p'], '')
            self.assertEqual(row['nota_global_1p'], '')
            self.assertEqual(row['desenlace_1p'], '')

    def test_ausente_aparece_en_csv(self):
        NotaParcial.objects.create(
            parcial=self.parcial, estudiante=self.est1, ausente=True,
        )
        NotaParcial.objects.create(
            parcial=self.parcial, estudiante=self.est2, puntaje=Decimal('8.00'),
        )
        rows = self._call_command(self.comision.id, self.parcial.id)
        fila_est1 = next(r for r in rows if 'exp_est1' not in r['id_anon'])
        # Identificar la fila del ausente por desenlace
        ausentes = [r for r in rows if r['ausente_1p'] == 'True']
        self.assertEqual(len(ausentes), 1)
        self.assertEqual(ausentes[0]['desenlace_1p'], 'Ausente')

    def test_desenlace_promocion(self):
        NotaParcial.objects.create(
            parcial=self.parcial, estudiante=self.est1, puntaje=Decimal('8.50'),
        )
        rows = self._call_command(self.comision.id, self.parcial.id)
        promovidos = [r for r in rows if r['desenlace_1p'] == 'Promoción']
        self.assertEqual(len(promovidos), 1)

    def test_id_anon_no_expone_username(self):
        rows = self._call_command(self.comision.id)
        for row in rows:
            self.assertNotIn('exp_est1', row['id_anon'])
            self.assertNotIn('exp_est2', row['id_anon'])
```

- [ ] **Paso 3: Verificar que los tests fallan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test cursos.tests --verbosity=2 2>&1 | head -15
```

Esperado: `CommandError: Unknown command: 'exportar_cohorte'`

- [ ] **Paso 4: Implementar el command**

Crear `cursos/management/commands/exportar_cohorte.py`:

```python
"""Management command: exportar_cohorte

Exporta los datos de una comisión en formato CSV compatible con el Excel
histórico de la Memoria Profesional (juntas_con_notas_anon.xlsx), con
columnas adicionales de uso de plataforma para el análisis de impacto.

Uso:
    python manage.py exportar_cohorte <comision_id>
    python manage.py exportar_cohorte <comision_id> --parcial-id <id>
    python manage.py exportar_cohorte <comision_id> --parcial-id <id> --output cohorte.csv
"""
import csv
import sys

from django.core.management.base import BaseCommand, CommandError

from accounts.models import EncuestaEstudiante
from analiticas.calculos import (
    calcular_desenlace_parcial,
    calcular_nse,
    calcular_puntaje_logicas,
    calcular_uso_plataforma_antes_parcial,
)
from cursos.models import Comision, NotaParcial, Parcial


class Command(BaseCommand):
    help = 'Exporta datos de una comisión como CSV comparable con la serie histórica.'

    def add_arguments(self, parser):
        parser.add_argument('comision_id', type=int)
        parser.add_argument('--parcial-id', type=int, default=None,
                            help='ID del 1er parcial para incluir desenlace y uso.')
        parser.add_argument('--output', type=str, default=None,
                            help='Ruta del archivo de salida. Por defecto: stdout.')

    def handle(self, *args, **options):
        comision_id = options['comision_id']
        parcial_id = options['parcial_id']

        try:
            comision = Comision.objects.get(pk=comision_id)
        except Comision.DoesNotExist:
            raise CommandError(f'Comisión {comision_id} no existe.')

        parcial = None
        if parcial_id:
            try:
                parcial = Parcial.objects.get(pk=parcial_id, comision=comision)
            except Parcial.DoesNotExist:
                raise CommandError(f'Parcial {parcial_id} no pertenece a la comisión {comision_id}.')

        inscripciones = (
            comision.inscripciones
            .select_related('estudiante')
            .order_by('estudiante__last_name', 'estudiante__first_name', 'estudiante__username')
        )

        # Precargar encuestas y notas
        estudiante_ids = [i.estudiante_id for i in inscripciones]
        encuestas = {
            e.estudiante_id: e
            for e in EncuestaEstudiante.objects.filter(estudiante_id__in=estudiante_ids)
        }
        notas = {}
        if parcial:
            notas = {
                n.estudiante_id: n
                for n in NotaParcial.objects.filter(parcial=parcial)
            }

        # Determinar año/cuatrimestre desde el nombre o fecha del parcial
        # (usar año actual como fallback)
        import datetime
        anio = datetime.date.today().year
        cuatri = 1 if datetime.date.today().month <= 6 else 2

        out_file = open(options['output'], 'w', newline='', encoding='utf-8') \
            if options['output'] else self.stdout

        try:
            writer = csv.DictWriter(out_file, fieldnames=_COLUMNAS, extrasaction='ignore')
            writer.writeheader()

            for idx, inscripcion in enumerate(inscripciones, start=1):
                est = inscripcion.estudiante
                encuesta = encuestas.get(est.pk)
                nota = notas.get(est.pk)

                row = _fila_base(est, idx, anio, cuatri, encuesta)

                if nota:
                    row['ausente_1p'] = nota.ausente
                    row['nota_global_1p'] = '' if nota.puntaje is None else nota.puntaje
                    row['nota_logica_1p'] = '' if nota.puntaje_logica is None else nota.puntaje_logica
                    row['desenlace_1p'] = calcular_desenlace_parcial(nota) or ''

                if parcial and encuesta and encuesta.estudiante.consentimiento_pedagogico:
                    uso = calcular_uso_plataforma_antes_parcial(est, parcial)
                    row.update(uso)

                writer.writerow(row)
        finally:
            if options['output']:
                out_file.close()

        if options['output']:
            self.stdout.write(self.style.SUCCESS(
                f'Exportado: {options["output"]} ({inscripciones.count()} estudiantes)'
            ))


_ERROR_CATS = [
    'tautologia', 'contradiccion', 'polaridad', 'mas_fuerte', 'mas_debil',
    'equivalente_alt', 'error_parcial_1', 'error_parcial_2', 'error_sistemico',
    'variables_extra', 'variables_menos',
]

_COLUMNAS = [
    # Bloque A — Encuesta (réplica del Excel histórico)
    'id_anon', 'edad', 'facultad', 'carrera',
    'origen_caba_gba', 'vive_en', 'mudado_con_familia', 'mudado_para_trabajar_estudiar',
    'tiempo_mudado', 'desde_donde', 'provincia_origen', 'pais_origen',
    'tiene_cud', 'con_quien_vive', 'tiempo_viaje_puan',
    'situacion_laboral', 'dias_trabaja',
    'acceso_internet', 'celular', 'tablet', 'pc_escritorio', 'computadora_portatil',
    'tiempo_desde_secundaria', 'tipo_escuela',
    'estudios_superiores', 'termino_cbc_anterior', 'se_recibio_uba', 'se_recibio_fuera_uba',
    'hizo_uba_xxi', 'tiempo_en_cbc', 'interrupcion_cbc',
    'ya_curso_ipc', 'motivo_no_termino_ipc', 'materias_aprobadas',
    'acertijo_silogismo', 'acertijo_cirugia_respuesta', 'acertijo_hilera',
    'puntaje_logicas', 'puntaje_nse', 'categoria_nse',
    'anio', 'cuatri',
    # Bloque B — Desenlace 1P
    'ausente_1p', 'nota_global_1p', 'nota_logica_1p', 'desenlace_1p',
    # Bloque C — Uso de plataforma
    'intentos_totales', 'ejercicios_distintos', 'practicas_abiertas',
    'ejercicios_resueltos', 'tasa_exito', 'promedio_intentos_hasta_correcto',
    'dias_activos', 'dias_primer_uso_hasta_1p', 'dias_ultimo_uso_hasta_1p',
] + [f'err_{c}' for c in _ERROR_CATS]


def _fila_base(est, idx, anio, cuatri, encuesta):
    """Construye la fila base con datos de encuesta o vacíos si no hay encuesta."""
    import datetime
    row = {col: '' for col in _COLUMNAS}
    row['id_anon'] = f'{anio}-{cuatri}-{idx}'
    row['anio'] = anio
    row['cuatri'] = cuatri

    # Bloques de desenlace vacíos por defecto
    row['ausente_1p'] = ''
    row['nota_global_1p'] = ''
    row['nota_logica_1p'] = ''
    row['desenlace_1p'] = ''

    # Bloque C vacío por defecto
    for col in ['intentos_totales', 'ejercicios_distintos', 'practicas_abiertas',
                'ejercicios_resueltos', 'tasa_exito', 'promedio_intentos_hasta_correcto',
                'dias_activos', 'dias_primer_uso_hasta_1p', 'dias_ultimo_uso_hasta_1p']:
        row[col] = ''
    for cat in _ERROR_CATS:
        row[f'err_{cat}'] = ''

    if not encuesta:
        return row

    # Edad al inicio del cuatrimestre
    if encuesta.fecha_nacimiento:
        ref = datetime.date(anio, 3 if cuatri == 1 else 8, 1)
        edad = (ref - encuesta.fecha_nacimiento).days // 365
        row['edad'] = edad

    row['facultad'] = encuesta.facultad or ''
    row['carrera'] = encuesta.carrera or ''
    row['origen_caba_gba'] = encuesta.origen_caba_gba if encuesta.origen_caba_gba is not None else ''
    row['vive_en'] = encuesta.vive_en or ''
    row['mudado_con_familia'] = encuesta.mudado_con_familia if encuesta.mudado_con_familia is not None else ''
    row['mudado_para_trabajar_estudiar'] = (
        encuesta.mudado_para_trabajar_estudiar
        if encuesta.mudado_para_trabajar_estudiar is not None else ''
    )
    row['tiempo_mudado'] = encuesta.tiempo_mudado or ''
    row['desde_donde'] = encuesta.desde_donde or ''
    row['provincia_origen'] = encuesta.provincia_origen or ''
    row['pais_origen'] = encuesta.pais_origen or ''
    row['tiene_cud'] = encuesta.tiene_cud if encuesta.tiene_cud is not None else ''
    row['con_quien_vive'] = encuesta.con_quien_vive or ''
    row['tiempo_viaje_puan'] = encuesta.tiempo_viaje_puan or ''
    row['situacion_laboral'] = encuesta.situacion_laboral or ''
    row['dias_trabaja'] = encuesta.dias_trabaja or ''

    dispositivos = encuesta.dispositivos or {}
    row['celular'] = dispositivos.get('celular', '')
    row['tablet'] = dispositivos.get('tablet', '')
    row['pc_escritorio'] = dispositivos.get('pc', '')
    row['computadora_portatil'] = dispositivos.get('laptop', '')
    row['acceso_internet'] = ';'.join(encuesta.acceso_internet or [])

    row['tiempo_desde_secundaria'] = encuesta.tiempo_desde_secundaria or ''
    row['tipo_escuela'] = encuesta.tipo_escuela or ''
    row['estudios_superiores'] = encuesta.estudios_superiores or ''
    row['termino_cbc_anterior'] = encuesta.termino_cbc_anterior if encuesta.termino_cbc_anterior is not None else ''
    row['se_recibio_uba'] = encuesta.se_recibio_uba if encuesta.se_recibio_uba is not None else ''
    row['se_recibio_fuera_uba'] = encuesta.se_recibio_fuera_uba if encuesta.se_recibio_fuera_uba is not None else ''
    row['hizo_uba_xxi'] = encuesta.hizo_uba_xxi if encuesta.hizo_uba_xxi is not None else ''
    row['tiempo_en_cbc'] = encuesta.tiempo_en_cbc or ''
    row['interrupcion_cbc'] = encuesta.interrupcion_cbc or ''
    row['ya_curso_ipc'] = encuesta.ya_curso_ipc if encuesta.ya_curso_ipc is not None else ''
    row['motivo_no_termino_ipc'] = encuesta.motivo_no_termino_ipc or ''
    row['materias_aprobadas'] = encuesta.materias_aprobadas if encuesta.materias_aprobadas is not None else ''

    row['acertijo_silogismo'] = encuesta.acertijo_silogismo or ''
    row['acertijo_cirugia_respuesta'] = encuesta.acertijo_cirugia or ''
    row['acertijo_hilera'] = encuesta.acertijo_hilera or ''
    row['puntaje_logicas'] = calcular_puntaje_logicas(encuesta)

    puntaje_nse, cat_nse = calcular_nse(encuesta)
    row['puntaje_nse'] = puntaje_nse
    row['categoria_nse'] = cat_nse

    return row
```

- [ ] **Paso 5: Verificar que los tests pasan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test cursos.tests --verbosity=2
```

Esperado: todos PASS.

- [ ] **Paso 6: Verificar uso manual**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py exportar_cohorte --help
```

Esperado: muestra la ayuda con `comision_id`, `--parcial-id`, `--output`.

- [ ] **Paso 7: Commit**

```bash
git add cursos/management/ cursos/tests.py
git commit -m "feat(cursos): management command exportar_cohorte (CSV comparable con serie histórica)"
```

---

## Task 7: UI — ausente + puntaje_logica en `parcial_notas`

**Files:**
- Modify: `docentes/views.py`
- Modify: `templates/docentes/parcial_notas.html`
- Modify: `docentes/tests.py`

- [ ] **Paso 1: Escribir el test**

Agregar en `docentes/tests.py`, dentro de `class ParcialTests`:

```python
def test_guardar_ausente_pone_ausente_true_y_notas_null(self):
    self.client.login(username='doc_parcial', password='clave123')
    parcial = Parcial.objects.create(
        comision=self.comision, nombre='P1',
        fecha=datetime.date(2026, 6, 15), puntaje_total='10.00',
    )
    nota1 = NotaParcial.objects.create(parcial=parcial, estudiante=self.est1)
    nota2 = NotaParcial.objects.create(parcial=parcial, estudiante=self.est2)

    resp = self.client.post(
        reverse('docentes:parcial_notas', kwargs={'parcial_id': parcial.id}),
        {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '2',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            f'form-0-id': str(nota1.id),
            f'form-0-ausente': 'on',        # checkbox marcado
            f'form-0-puntaje': '',
            f'form-0-puntaje_logica': '',
            f'form-1-id': str(nota2.id),
            f'form-1-puntaje': '7.50',
            f'form-1-puntaje_logica': '5.00',
        },
    )
    self.assertEqual(resp.status_code, 302)
    nota1.refresh_from_db()
    nota2.refresh_from_db()
    self.assertTrue(nota1.ausente)
    self.assertIsNone(nota1.puntaje)
    self.assertEqual(nota2.puntaje, Decimal('7.50'))
    self.assertEqual(nota2.puntaje_logica, Decimal('5.00'))

def test_conteo_cargadas_incluye_ausentes(self):
    self.client.login(username='doc_parcial', password='clave123')
    parcial = Parcial.objects.create(
        comision=self.comision, nombre='P1',
        fecha=datetime.date(2026, 6, 15), puntaje_total='10.00',
    )
    NotaParcial.objects.create(parcial=parcial, estudiante=self.est1, ausente=True)
    NotaParcial.objects.create(parcial=parcial, estudiante=self.est2)

    resp = self.client.get(
        reverse('docentes:parcial_notas', kwargs={'parcial_id': parcial.id})
    )
    self.assertEqual(resp.status_code, 200)
    # 1 ausente cuenta como cargada, 1 pendiente
    self.assertEqual(resp.context['cargadas'], 1)
    self.assertEqual(resp.context['total'], 2)
```

- [ ] **Paso 2: Verificar que los tests fallan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test docentes.tests.ParcialTests.test_guardar_ausente_pone_ausente_true_y_notas_null docentes.tests.ParcialTests.test_conteo_cargadas_incluye_ausentes --verbosity=2
```

Esperado: FAIL (el formset no incluye `ausente` y el conteo no considera ausentes).

- [ ] **Paso 3: Actualizar la vista**

En `docentes/views.py`, en la función `parcial_notas`, reemplazar el cálculo de `cargadas`:

```python
    total = qs.count()
    cargadas = qs.filter(
        models.Q(puntaje__isnull=False) | models.Q(ausente=True)
    ).count()
```

Asegurarse de que `from django.db import models` está importado en la vista (o usar `Q` directamente):

```python
from django.db.models import Q
# ...
    cargadas = qs.filter(Q(puntaje__isnull=False) | Q(ausente=True)).count()
```

- [ ] **Paso 4: Actualizar el template**

En `templates/docentes/parcial_notas.html`, reemplazar el bloque de la tabla completo:

```html
<table style="width: 100%; border-collapse: collapse; font-size: 0.93rem;">
  <thead>
    <tr style="border-bottom: 2px solid #ddd; text-align: left;">
      <th style="padding: 0.5rem 0.75rem;">Estudiante</th>
      <th style="padding: 0.5rem 0.75rem; width: 3rem; text-align: center;">Ausente</th>
      <th style="padding: 0.5rem 0.75rem; width: 9rem;">Nota global</th>
      <th style="padding: 0.5rem 0.75rem; width: 9rem;">Nota lógica</th>
      <th style="padding: 0.5rem 0.75rem; width: 7rem; text-align: center;">Estado</th>
    </tr>
  </thead>
  <tbody>
    {% for form in formset %}
      {% with est=form.instance.estudiante cargada=form.instance.puntaje es_ausente=form.instance.ausente %}
      <tr style="border-bottom: 1px solid #eee;{% if not cargada and not es_ausente %} background-color: rgba(255, 193, 7, 0.08);{% endif %}">
        {{ form.id }}
        <td style="padding: 0.5rem 0.75rem; font-weight: 500;">
          {% if est.last_name and est.first_name %}
            {{ est.last_name }}, {{ est.first_name }}
          {% else %}
            {{ est.username }}
          {% endif %}
          {% if est.last_name or est.first_name %}
            <br><span style="font-size: 0.78rem; color: #999; font-weight: 400;">@{{ est.username }}</span>
          {% endif %}
        </td>
        <td style="padding: 0.4rem 0.75rem; text-align: center;">
          {{ form.ausente }}
        </td>
        <td style="padding: 0.4rem 0.75rem;">
          {{ form.puntaje }}
          {% if form.puntaje.errors %}
            <span style="color: #b00020; font-size: 0.8rem; display: block;">{{ form.puntaje.errors|striptags }}</span>
          {% endif %}
        </td>
        <td style="padding: 0.4rem 0.75rem;">
          {{ form.puntaje_logica }}
          {% if form.puntaje_logica.errors %}
            <span style="color: #b00020; font-size: 0.8rem; display: block;">{{ form.puntaje_logica.errors|striptags }}</span>
          {% endif %}
        </td>
        <td style="padding: 0.4rem 0.75rem; text-align: center;">
          {% if es_ausente %}
            <span style="background: #f8d7da; color: #842029; font-size: 0.78rem; padding: 0.15rem 0.55rem; border-radius: 10px; white-space: nowrap;">
              Ausente
            </span>
          {% elif cargada is not None %}
            <span style="background: #d4edda; color: #155724; font-size: 0.78rem; padding: 0.15rem 0.55rem; border-radius: 10px; white-space: nowrap;">
              Cargada
            </span>
          {% else %}
            <span style="background: #fff3cd; color: #856404; font-size: 0.78rem; padding: 0.15rem 0.55rem; border-radius: 10px; white-space: nowrap;">
              Pendiente
            </span>
          {% endif %}
        </td>
      </tr>
      {% endwith %}
    {% empty %}
      <tr>
        <td colspan="5" style="padding: 1rem; color: #888; text-align: center;">
          Sin estudiantes inscriptos en esta comisión.
        </td>
      </tr>
    {% endfor %}
  </tbody>
</table>
```

- [ ] **Paso 5: Verificar que los tests pasan**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py test docentes.tests.ParcialTests --verbosity=2
```

Esperado: todos los tests de ParcialTests PASS (incluyendo los anteriores y los nuevos).

- [ ] **Paso 6: Verificar que manage.py check pasa**

```
C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe manage.py check
```

Esperado: `System check identified no issues (0 silenced).`

- [ ] **Paso 7: Commit**

```bash
git add docentes/views.py templates/docentes/parcial_notas.html docentes/tests.py
git commit -m "feat(docentes): UI parcial_notas con ausente, puntaje_logica y chip de estado"
```

---

## Self-review

**Cobertura del spec:**
- ✅ `NotaParcial.ausente` — Task 1
- ✅ `NotaParcial.puntaje_logica` — Task 1
- ✅ `Parcial.umbral_aprobacion/umbral_promocion` — Task 1
- ✅ `calcular_nse` — Task 3
- ✅ `calcular_puntaje_logicas` — Task 3
- ✅ `calcular_desenlace_parcial` — Task 4
- ✅ `calcular_uso_plataforma_antes_parcial` — Task 5
- ✅ Management command `exportar_cohorte` con Bloques A, B, C — Task 6
- ✅ UI ausente + puntaje_logica — Task 7
- ✅ Chip de estado: Pendiente/Ausente/Cargada — Task 7
- ✅ Conteo de cargadas incluye ausentes — Task 7

**Consistencia de tipos:**
- `calcular_nse` devuelve `(float, str)` — consistente en implementación y tests
- `calcular_desenlace_parcial` recibe `NotaParcial` con atributo `.parcial` — válido dado que el ORM carga la FK
- `calcular_uso_plataforma_antes_parcial` usa `parcial.fecha` (DateField) para `datetime.combine` — correcto
- `_fila_base` en el command llama a `calcular_puntaje_logicas(encuesta)` — firma coincide con Task 3

**Sin placeholders:** Toda la implementación está completa con código real.
