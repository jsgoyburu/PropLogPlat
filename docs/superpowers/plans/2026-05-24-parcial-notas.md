# Carga de notas de parcial — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir a docentes crear parciales por comisión y cargar progresivamente las notas de lógica de cada estudiante desde una tabla editable.

**Architecture:** Dos modelos nuevos en `cursos` (`Parcial`, `NotaParcial`), cuatro vistas nuevas en `docentes`, y un panel nuevo en `comision_detail`. Al crear un parcial se pre-crean registros `NotaParcial(puntaje=null)` para todos los inscriptos. La tabla de notas usa `modelformset_factory` con guardado en bloque.

**Tech Stack:** Django ModelForms, modelformset_factory, Django messages framework, Bootstrap-compatible HTML inline styles (mismo patrón que el proyecto).

---

## Mapa de archivos

| Archivo | Acción | Qué cambia |
|---|---|---|
| `cursos/models.py` | Modificar | Agregar `Parcial` y `NotaParcial` |
| `cursos/admin.py` | Modificar | Registrar `Parcial` y `NotaParcial` |
| `cursos/migrations/0003_parcial_notaparcial.py` | Crear | Migración auto-generada |
| `docentes/forms.py` | Modificar | Agregar `ParcialForm` y `get_nota_parcial_formset()` |
| `docentes/views.py` | Modificar | Agregar 4 vistas nuevas + importar modelos |
| `docentes/urls.py` | Modificar | Agregar 4 URLs nuevas |
| `docentes/tests.py` | Modificar | Agregar `ParcialTests` |
| `templates/docentes/parcial_form.html` | Crear | Form crear/editar parcial |
| `templates/docentes/parcial_notas.html` | Crear | Tabla editable de notas |
| `templates/docentes/comision_detail.html` | Modificar | Panel "Parciales" |

---

## Task 1: Modelos `Parcial` y `NotaParcial`

**Files:**
- Modify: `cursos/models.py`
- Modify: `docentes/tests.py`

- [ ] **Step 1: Escribir test que falla — pre-creación de notas**

En `docentes/tests.py`, agregar al final:

```python
from cursos.models import Parcial, NotaParcial
import datetime


class ParcialTests(TestCase):
    def setUp(self):
        self.docente = _u('doc_parcial', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC Mañana')
        self.comision.docentes.add(self.docente)
        self.est1 = _u('est1_parcial')
        self.est2 = _u('est2_parcial')
        Inscripcion.objects.create(estudiante=self.est1, comision=self.comision)
        Inscripcion.objects.create(estudiante=self.est2, comision=self.comision)

    def test_crear_parcial_precrea_notas_para_todos_los_inscriptos(self):
        self.client.login(username='doc_parcial', password='clave123')
        resp = self.client.post(
            reverse('docentes:parcial_create', kwargs={'comision_id': self.comision.id}),
            {'nombre': 'Parcial 1', 'fecha': '2026-06-15', 'puntaje_total': '10.00'},
        )
        self.assertEqual(Parcial.objects.count(), 1)
        parcial = Parcial.objects.get()
        self.assertEqual(parcial.comision, self.comision)
        self.assertEqual(NotaParcial.objects.filter(parcial=parcial).count(), 2)
        notas = NotaParcial.objects.filter(parcial=parcial)
        self.assertTrue(all(n.puntaje is None for n in notas))

    def test_docente_externo_no_puede_crear_parcial(self):
        otro = _u('otro_docente', es_docente=True)
        self.client.login(username='otro_docente', password='clave123')
        resp = self.client.post(
            reverse('docentes:parcial_create', kwargs={'comision_id': self.comision.id}),
            {'nombre': 'Parcial 1', 'fecha': '2026-06-15', 'puntaje_total': '10.00'},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Parcial.objects.count(), 0)

    def test_guardar_notas_parciales(self):
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
                f'form-0-puntaje': '7.50',
                f'form-1-id': str(nota2.id),
                f'form-1-puntaje': '',
            },
        )
        self.assertEqual(resp.status_code, 302)
        nota1.refresh_from_db()
        nota2.refresh_from_db()
        self.assertEqual(nota1.puntaje, 7.50)
        self.assertIsNone(nota2.puntaje)

    def test_eliminar_parcial_elimina_notas(self):
        self.client.login(username='doc_parcial', password='clave123')
        parcial = Parcial.objects.create(
            comision=self.comision, nombre='P1',
            fecha=datetime.date(2026, 6, 15), puntaje_total='10.00',
        )
        NotaParcial.objects.create(parcial=parcial, estudiante=self.est1)
        resp = self.client.post(
            reverse('docentes:parcial_delete', kwargs={'parcial_id': parcial.id}),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Parcial.objects.count(), 0)
        self.assertEqual(NotaParcial.objects.count(), 0)
```

- [ ] **Step 2: Correr test para verificar que falla**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ParcialTests -v 2
```

Esperado: ERROR — `ImportError: cannot import name 'Parcial' from 'cursos.models'`

- [ ] **Step 3: Agregar `Parcial` y `NotaParcial` a `cursos/models.py`**

Al final del archivo, después de la clase `Inscripcion`:

```python
class Parcial(models.Model):
    """Instancia de evaluación parcial de lógica para una comisión.

    Cada comisión puede tener múltiples parciales (Parcial 1, Recuperatorio, etc.).
    Al crear un Parcial, se pre-crean NotaParcial(puntaje=null) para todos los
    estudiantes inscriptos en ese momento.
    """

    comision = models.ForeignKey(
        Comision,
        on_delete=models.CASCADE,
        related_name='parciales',
        verbose_name='comisión',
    )
    nombre = models.CharField(
        max_length=100,
        verbose_name='nombre',
        help_text='Ej: "Parcial 1", "Recuperatorio".',
    )
    fecha = models.DateField(verbose_name='fecha')
    puntaje_total = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='puntaje total (parte lógica)',
        help_text='Máximo posible de la parte de lógica.',
    )

    class Meta:
        verbose_name = 'parcial'
        verbose_name_plural = 'parciales'
        ordering = ['fecha', 'nombre']

    def __str__(self) -> str:
        return f'{self.nombre} — {self.comision}'


class NotaParcial(models.Model):
    """Nota de un estudiante en la parte de lógica de un parcial.

    puntaje=null significa que aún no fue cargada.
    """

    parcial = models.ForeignKey(
        Parcial,
        on_delete=models.CASCADE,
        related_name='notas',
        verbose_name='parcial',
    )
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notas_parciales',
        verbose_name='estudiante',
    )
    puntaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='puntaje',
    )

    class Meta:
        verbose_name = 'nota de parcial'
        verbose_name_plural = 'notas de parcial'
        unique_together = ['parcial', 'estudiante']
        ordering = ['estudiante__last_name', 'estudiante__first_name', 'estudiante__username']

    def __str__(self) -> str:
        return f'{self.estudiante} — {self.parcial}: {self.puntaje}'
```

- [ ] **Step 4: Correr tests para verificar que siguen fallando solo por falta de URLs**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ParcialTests -v 2
```

Esperado: fallo con `NoReverseMatch` (modelos existen, faltan URLs).

---

## Task 2: Migración

**Files:**
- Create: `cursos/migrations/0003_parcial_notaparcial.py` (auto-generado)

- [ ] **Step 1: Generar migración**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations cursos --name parcial_notaparcial
```

Esperado: `Migrations for 'cursos': cursos/migrations/0003_parcial_notaparcial.py`

- [ ] **Step 2: Verificar migración generada**

Revisar que `cursos/migrations/0003_parcial_notaparcial.py` contiene `CreateModel` para `Parcial` y `NotaParcial` con todos los campos, la FK a `Comision`, la FK a `settings.AUTH_USER_MODEL`, y `unique_together`.

- [ ] **Step 3: Aplicar migración**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py migrate cursos
```

Esperado: `Applying cursos.0003_parcial_notaparcial... OK`

- [ ] **Step 4: Commit**

```
git add cursos/models.py cursos/migrations/0003_parcial_notaparcial.py
git commit -m "feat(cursos): agregar modelos Parcial y NotaParcial"
```

---

## Task 3: Admin

**Files:**
- Modify: `cursos/admin.py`

- [ ] **Step 1: Registrar modelos en admin**

Reemplazar el contenido de `cursos/admin.py`:

```python
"""Admin de la app cursos."""

from django.contrib import admin

from cursos.models import Comision, Inscripcion, NotaParcial, Parcial


class InscripcionInline(admin.TabularInline):
    """Inline para ver estudiantes inscriptos desde la comisión."""

    model = Inscripcion
    extra = 0
    autocomplete_fields = ['estudiante']


class NotaParcialInline(admin.TabularInline):
    model = NotaParcial
    extra = 0
    fields = ['estudiante', 'puntaje']
    autocomplete_fields = ['estudiante']


@admin.register(Comision)
class ComisionAdmin(admin.ModelAdmin):
    """Admin para Comision con inline de inscripciones."""

    list_display = ('nombre',)
    search_fields = ('nombre',)
    filter_horizontal = ('docentes',)
    inlines = [InscripcionInline]


@admin.register(Inscripcion)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'comision', 'fecha_inscripcion')
    list_filter = ('comision',)
    search_fields = ('estudiante__username', 'comision__nombre')


@admin.register(Parcial)
class ParcialAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'comision', 'fecha', 'puntaje_total')
    list_filter = ('comision',)
    search_fields = ('nombre', 'comision__nombre')
    inlines = [NotaParcialInline]


@admin.register(NotaParcial)
class NotaParcialAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'parcial', 'puntaje')
    list_filter = ('parcial__comision', 'parcial')
    search_fields = ('estudiante__username', 'estudiante__last_name')
```

- [ ] **Step 2: Verificar que el admin levanta sin errores**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py check
```

Esperado: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```
git add cursos/admin.py
git commit -m "feat(cursos): registrar Parcial y NotaParcial en admin"
```

---

## Task 4: Form `ParcialForm` y helper de formset

**Files:**
- Modify: `docentes/forms.py`

- [ ] **Step 1: Agregar imports y formularios al final de `docentes/forms.py`**

Primero, agregar al bloque de imports existente (al comienzo del archivo):

```python
# Agregar a la línea que importa desde cursos.models:
from cursos.models import Comision, NotaParcial, Parcial
```

Luego, agregar al final del archivo:

```python
class ParcialForm(forms.ModelForm):
    """Formulario de creación/edición de parciales (metadatos, sin notas)."""

    class Meta:
        model = Parcial
        fields = ['nombre', 'fecha', 'puntaje_total']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
        }


def get_nota_parcial_formset(extra=0):
    """Devuelve un FormSet class para editar puntajes de NotaParcial."""
    from django.forms import modelformset_factory
    return modelformset_factory(
        NotaParcial,
        fields=['puntaje'],
        extra=extra,
    )
```

- [ ] **Step 2: Verificar que el import en forms.py no rompe nada**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py check
```

Esperado: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```
git add docentes/forms.py
git commit -m "feat(docentes): agregar ParcialForm y get_nota_parcial_formset"
```

---

## Task 5: Vista `parcial_create` + URL + template

**Files:**
- Modify: `docentes/views.py`
- Modify: `docentes/urls.py`
- Create: `templates/docentes/parcial_form.html`

- [ ] **Step 1: Agregar imports a `docentes/views.py`**

En la línea que importa desde `cursos.models`, agregar `Parcial` y `NotaParcial`:

```python
from cursos.models import Comision, Inscripcion, NotaParcial, Parcial
```

En la línea que importa desde `.forms`, agregar `ParcialForm` y `get_nota_parcial_formset`:

```python
from .forms import (
    ComisionForm,
    DocenteComisionForm,
    EjercicioForm,
    EjercicioPracticaForm,
    EstudianteCreateForm,
    EstudianteEditForm,
    get_nota_parcial_formset,
    ImportarEstudiantesForm,
    ParcialForm,
    PracticaComisionForm,
    PracticaForm,
)
```

- [ ] **Step 2: Agregar vista `parcial_create` en `docentes/views.py`**

Agregar antes de la primera vista de ejercicios (buscar `def ejercicio_create`):

```python
@login_required
def parcial_create(request, comision_id):
    """Crea un nuevo parcial para la comisión y pre-crea notas null para inscriptos."""
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    if request.method == 'POST':
        form = ParcialForm(request.POST)
        if form.is_valid():
            parcial = form.save(commit=False)
            parcial.comision = comision
            parcial.save()
            inscripciones = comision.inscripciones.select_related('estudiante').all()
            NotaParcial.objects.bulk_create([
                NotaParcial(parcial=parcial, estudiante=i.estudiante)
                for i in inscripciones
            ])
            messages.success(request, f'Parcial "{parcial.nombre}" creado con {inscripciones.count()} notas pre-cargadas.')
            return redirect('docentes:parcial_notas', parcial_id=parcial.id)
    else:
        form = ParcialForm()

    return render(request, 'docentes/parcial_form.html', {
        'form': form,
        'comision': comision,
        'modo': 'crear',
    })
```

- [ ] **Step 3: Agregar URL en `docentes/urls.py`**

Agregar estas 4 líneas al final de `urlpatterns` (antes del cierre de `]`):

```python
    path('comisiones/<int:comision_id>/parciales/nuevo/', views.parcial_create, name='parcial_create'),
    path('parciales/<int:parcial_id>/editar/', views.parcial_edit, name='parcial_edit'),
    path('parciales/<int:parcial_id>/eliminar/', views.parcial_delete, name='parcial_delete'),
    path('parciales/<int:parcial_id>/notas/', views.parcial_notas, name='parcial_notas'),
```

- [ ] **Step 4: Crear template `templates/docentes/parcial_form.html`**

```html
{% extends 'base.html' %}

{% block title %}
  {% if modo == 'crear' %}Nuevo parcial{% else %}Editar parcial{% endif %} · {{ comision.nombre }}
{% endblock %}

{% block content %}
<div class="container">

  <div class="card">
    <div class="breadcrumb">
      <a href="{% url 'docentes:comisiones_list' %}">Panel docente</a>
      &rsaquo; <a href="{% url 'docentes:comision_detail' comision.id %}">{{ comision.nombre }}</a>
      &rsaquo; {% if modo == 'crear' %}Nuevo parcial{% else %}Editar parcial{% endif %}
    </div>

    <h1 style="margin: 0.25rem 0 1rem;">
      {% if modo == 'crear' %}Nuevo parcial{% else %}Editar parcial{% endif %}
    </h1>

    <form method="post">
      {% csrf_token %}

      <div style="display: grid; gap: 0.75rem; max-width: 28rem;">
        <div>
          <label style="font-weight: 500; display: block; margin-bottom: 0.25rem;">
            {{ form.nombre.label }}
          </label>
          {{ form.nombre }}
          {% if form.nombre.errors %}
            <span class="alert alert-error" style="display: block; margin-top: 0.3rem; padding: 0.4rem 0.6rem;">
              {{ form.nombre.errors|striptags }}
            </span>
          {% endif %}
        </div>

        <div>
          <label style="font-weight: 500; display: block; margin-bottom: 0.25rem;">
            {{ form.fecha.label }}
          </label>
          {{ form.fecha }}
          {% if form.fecha.errors %}
            <span class="alert alert-error" style="display: block; margin-top: 0.3rem; padding: 0.4rem 0.6rem;">
              {{ form.fecha.errors|striptags }}
            </span>
          {% endif %}
        </div>

        <div>
          <label style="font-weight: 500; display: block; margin-bottom: 0.25rem;">
            {{ form.puntaje_total.label }}
          </label>
          {{ form.puntaje_total }}
          {% if form.puntaje_total.errors %}
            <span class="alert alert-error" style="display: block; margin-top: 0.3rem; padding: 0.4rem 0.6rem;">
              {{ form.puntaje_total.errors|striptags }}
            </span>
          {% endif %}
          <small style="color: #888; font-size: 0.82rem;">Máximo posible de la parte de lógica (puede ser decimal, ej: 3.50)</small>
        </div>
      </div>

      <div style="margin-top: 1.25rem; display: flex; gap: 0.6rem;">
        <button type="submit" class="btn btn-primary">
          {% if modo == 'crear' %}Crear parcial{% else %}Guardar cambios{% endif %}
        </button>
        <a class="btn btn-secondary" href="{% url 'docentes:comision_detail' comision.id %}">Cancelar</a>
      </div>
    </form>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5: Correr los tests de `parcial_create`**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ParcialTests.test_crear_parcial_precrea_notas_para_todos_los_inscriptos docentes.tests.ParcialTests.test_docente_externo_no_puede_crear_parcial -v 2
```

Esperado: 2 tests PASS.

- [ ] **Step 6: Commit**

```
git add docentes/views.py docentes/urls.py templates/docentes/parcial_form.html
git commit -m "feat(docentes): vista parcial_create con pre-creación de notas"
```

---

## Task 6: Vistas `parcial_edit` y `parcial_delete`

**Files:**
- Modify: `docentes/views.py`

- [ ] **Step 1: Agregar vista `parcial_edit` en `docentes/views.py`** (a continuación de `parcial_create`):

```python
@login_required
def parcial_edit(request, parcial_id):
    """Edita metadatos del parcial (nombre, fecha, puntaje_total). No toca las notas."""
    _require_docente(request.user)
    parcial = get_object_or_404(Parcial, pk=parcial_id)
    comision = parcial.comision
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    if request.method == 'POST':
        form = ParcialForm(request.POST, instance=parcial)
        if form.is_valid():
            form.save()
            messages.success(request, f'Parcial "{parcial.nombre}" actualizado.')
            return redirect('docentes:comision_detail', comision_id=comision.id)
    else:
        form = ParcialForm(instance=parcial)

    return render(request, 'docentes/parcial_form.html', {
        'form': form,
        'comision': comision,
        'modo': 'editar',
        'parcial': parcial,
    })
```

- [ ] **Step 2: Agregar vista `parcial_delete` en `docentes/views.py`** (a continuación de `parcial_edit`):

```python
@login_required
@require_POST
def parcial_delete(request, parcial_id):
    """Elimina el parcial y todas sus notas (CASCADE)."""
    _require_docente(request.user)
    parcial = get_object_or_404(Parcial, pk=parcial_id)
    comision = parcial.comision
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    nombre = parcial.nombre
    parcial.delete()
    messages.success(request, f'Parcial "{nombre}" eliminado.')
    return redirect('docentes:comision_detail', comision_id=comision.id)
```

- [ ] **Step 3: Correr test de eliminación**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ParcialTests.test_eliminar_parcial_elimina_notas -v 2
```

Esperado: PASS.

- [ ] **Step 4: Commit**

```
git add docentes/views.py
git commit -m "feat(docentes): vistas parcial_edit y parcial_delete"
```

---

## Task 7: Vista `parcial_notas` + template de tabla

**Files:**
- Modify: `docentes/views.py`
- Create: `templates/docentes/parcial_notas.html`

- [ ] **Step 1: Agregar vista `parcial_notas` en `docentes/views.py`** (a continuación de `parcial_delete`):

```python
@login_required
def parcial_notas(request, parcial_id):
    """Tabla editable para cargar progresivamente las notas de lógica."""
    _require_docente(request.user)
    parcial = get_object_or_404(Parcial, pk=parcial_id)
    comision = parcial.comision
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    qs = (
        NotaParcial.objects
        .filter(parcial=parcial)
        .select_related('estudiante')
        .order_by('estudiante__last_name', 'estudiante__first_name', 'estudiante__username')
    )
    NotaParcialFormSet = get_nota_parcial_formset()

    if request.method == 'POST':
        formset = NotaParcialFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            messages.success(request, 'Notas guardadas.')
            return redirect('docentes:parcial_notas', parcial_id=parcial_id)
    else:
        formset = NotaParcialFormSet(queryset=qs)

    total = qs.count()
    cargadas = qs.filter(puntaje__isnull=False).count()

    return render(request, 'docentes/parcial_notas.html', {
        'parcial': parcial,
        'comision': comision,
        'formset': formset,
        'total': total,
        'cargadas': cargadas,
    })
```

- [ ] **Step 2: Crear template `templates/docentes/parcial_notas.html`**

```html
{% extends 'base.html' %}

{% block title %}Notas — {{ parcial.nombre }} · {{ comision.nombre }}{% endblock %}

{% block content %}
<div class="container-wide">

  <!-- Encabezado -->
  <div class="card">
    <div class="breadcrumb">
      <a href="{% url 'docentes:comisiones_list' %}">Panel docente</a>
      &rsaquo; <a href="{% url 'docentes:comision_detail' comision.id %}">{{ comision.nombre }}</a>
      &rsaquo; {{ parcial.nombre }}
    </div>

    <div style="display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.5rem;">
      <div>
        <h1 style="margin: 0.25rem 0 0.25rem;">{{ parcial.nombre }}</h1>
        <p style="margin: 0; color: #555; font-size: 0.9rem;">
          {{ comision.nombre }} &nbsp;·&nbsp; {{ parcial.fecha|date:"j \d\e N \d\e Y" }}
          &nbsp;·&nbsp; Puntaje total (lógica): <strong>{{ parcial.puntaje_total }}</strong>
        </p>
      </div>
      <div style="text-align: right;">
        <div style="font-size: 1.1rem; font-weight: 600; color: {% if cargadas == total %}#2a7a2a{% else %}#c07000{% endif %};">
          {{ cargadas }} / {{ total }} notas cargadas
        </div>
        <a href="{% url 'docentes:parcial_edit' parcial.id %}"
           style="font-size: 0.82rem; color: #555;">Editar parcial</a>
      </div>
    </div>

    {% if messages %}
      {% for msg in messages %}
        <div class="alert alert-{{ msg.tags }}" style="margin-top: 0.75rem;">{{ msg }}</div>
      {% endfor %}
    {% endif %}
  </div>

  <!-- Tabla de notas -->
  <div class="card" style="margin-top: 1rem;">
    <form method="post">
      {% csrf_token %}
      {{ formset.management_form }}

      <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; font-size: 0.93rem;">
          <thead>
            <tr style="border-bottom: 2px solid #ddd; text-align: left;">
              <th style="padding: 0.5rem 0.75rem;">Estudiante</th>
              <th style="padding: 0.5rem 0.75rem; width: 10rem;">Nota</th>
              <th style="padding: 0.5rem 0.75rem; width: 8rem; text-align: center;">Estado</th>
            </tr>
          </thead>
          <tbody>
            {% for form in formset %}
              {% with est=form.instance.estudiante cargada=form.instance.puntaje %}
              <tr style="border-bottom: 1px solid #eee;{% if not cargada %} background-color: rgba(255, 193, 7, 0.08);{% endif %}">
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
                <td style="padding: 0.4rem 0.75rem;">
                  {{ form.puntaje }}
                  {% if form.puntaje.errors %}
                    <span style="color: #b00020; font-size: 0.8rem; display: block;">{{ form.puntaje.errors|striptags }}</span>
                  {% endif %}
                </td>
                <td style="padding: 0.4rem 0.75rem; text-align: center;">
                  {% if cargada is not None %}
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
                <td colspan="3" style="padding: 1rem; color: #888; text-align: center;">
                  Sin estudiantes inscriptos en esta comisión.
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>

      {% if formset.forms %}
        <div style="margin-top: 1rem; display: flex; gap: 0.6rem; align-items: center;">
          <button type="submit" class="btn btn-primary">Guardar</button>
          <a class="btn btn-secondary" href="{% url 'docentes:comision_detail' comision.id %}">Volver a la comisión</a>
        </div>
      {% endif %}
    </form>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 3: Correr test de guardado de notas**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ParcialTests.test_guardar_notas_parciales -v 2
```

Esperado: PASS.

- [ ] **Step 4: Correr todos los tests de `ParcialTests`**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ParcialTests -v 2
```

Esperado: 4 tests PASS.

- [ ] **Step 5: Commit**

```
git add docentes/views.py templates/docentes/parcial_notas.html
git commit -m "feat(docentes): vista parcial_notas con formset editable"
```

---

## Task 8: Panel de parciales en `comision_detail`

**Files:**
- Modify: `docentes/views.py` (función `comision_detail`)
- Modify: `templates/docentes/comision_detail.html`

- [ ] **Step 1: Agregar `parciales` al contexto de `comision_detail`**

En `docentes/views.py`, dentro de la función `comision_detail`, agregar ANTES del `return render(...)`:

```python
    parciales = (
        Parcial.objects
        .filter(comision=comision)
        .order_by('fecha', 'nombre')
        .annotate(
            total_notas=Count('notas'),
            notas_cargadas=Count('notas', filter=Q(notas__puntaje__isnull=False)),
        )
    )
```

Y agregar al diccionario del `return render(...)`:

```python
        'parciales': parciales,
```

También agregar los imports necesarios al comienzo del archivo si no están ya:

```python
from django.db.models import Count, F, Max, Prefetch, Q, Subquery, OuterRef
```

`Count` y `Q` ya están importados. Verificar que `Parcial` y `NotaParcial` estén en el import de `cursos.models` (ya se hizo en Task 5).

- [ ] **Step 2: Agregar panel "Parciales" en `comision_detail.html`**

Insertar el siguiente bloque DESPUÉS del cierre del panel de Prácticas (`</div>`) y ANTES del panel de Progreso. Buscar el comentario `<!-- ── Progreso por estudiante ─────────────────────────────── -->` e insertar antes de esa línea:

```html
  <!-- ── Parciales ─────────────────────────────────────────── -->
  <details class="card panel-card">
    <summary style="display: flex; justify-content: space-between; align-items: center; cursor: pointer; list-style: none; margin-bottom: 0;">
      <span style="display: flex; align-items: center; gap: 0.4rem;">
        <span class="panel-chevron" style="font-size: 0.7rem; opacity: 0.5; transition: transform 0.15s;">▶</span>
        <h2 style="margin: 0;">Parciales</h2>
      </span>
      <span style="font-size: 0.85rem; color: #888;">{{ parciales|length }} parcial{{ parciales|length|pluralize:"es" }}</span>
    </summary>
    <div style="margin-top: 1rem;">

      <div style="display: flex; justify-content: flex-end; margin-bottom: 0.75rem;">
        <a class="btn btn-primary"
           href="{% url 'docentes:parcial_create' comision.id %}"
           style="font-size: 0.85rem; padding: 0.3rem 0.9rem;">
          + Nuevo parcial
        </a>
      </div>

      {% if parciales %}
        <div class="stat-row stat-header" style="grid-template-columns: 1.5fr 0.8fr 0.8fr 1fr auto;">
          <span>Nombre</span>
          <span>Fecha</span>
          <span>Puntaje máx.</span>
          <span class="stat-num">Notas cargadas</span>
          <span></span>
        </div>
        {% for p in parciales %}
          <div class="stat-row" style="grid-template-columns: 1.5fr 0.8fr 0.8fr 1fr auto; align-items: center;">
            <span style="font-weight: 500;">{{ p.nombre }}</span>
            <span style="color: #555; font-size: 0.9rem;">{{ p.fecha|date:"j/n/Y" }}</span>
            <span style="color: #555; font-size: 0.9rem;">{{ p.puntaje_total }}</span>
            <span class="stat-num">
              <span style="color: {% if p.notas_cargadas == p.total_notas and p.total_notas > 0 %}#2a7a2a{% else %}#c07000{% endif %}; font-weight: 600;">
                {{ p.notas_cargadas }}/{{ p.total_notas }}
              </span>
            </span>
            <span style="display: flex; gap: 0.4rem;">
              <a class="btn btn-primary"
                 href="{% url 'docentes:parcial_notas' p.id %}"
                 style="font-size: 0.8rem; padding: 0.2rem 0.7rem; white-space: nowrap;">
                Cargar notas
              </a>
              <a class="btn btn-secondary"
                 href="{% url 'docentes:parcial_edit' p.id %}"
                 style="font-size: 0.8rem; padding: 0.2rem 0.7rem;">
                Editar
              </a>
              <button class="btn btn-danger"
                      style="font-size: 0.8rem; padding: 0.2rem 0.7rem; white-space: nowrap;"
                      onclick="document.getElementById('confirm-parcial-{{ p.id }}').showModal()">
                Eliminar
              </button>
            </span>
          </div>

          <dialog id="confirm-parcial-{{ p.id }}"
                  style="border-radius: 8px; border: 1px solid #ccc; padding: 1.5rem; max-width: 24rem;">
            <p style="margin-top: 0;">
              ¿Eliminar el parcial <strong>{{ p.nombre }}</strong>?
              <br><small style="color: #666;">Se eliminarán también todas las notas cargadas. Esta acción no se puede deshacer.</small>
            </p>
            <div style="display: flex; gap: 0.6rem; justify-content: flex-end;">
              <button class="btn btn-secondary"
                      style="font-size: 0.85rem; padding: 0.3rem 0.9rem;"
                      onclick="this.closest('dialog').close()">
                Cancelar
              </button>
              <form method="post" action="{% url 'docentes:parcial_delete' p.id %}" style="display: inline;">
                {% csrf_token %}
                <button type="submit" class="btn btn-danger"
                        style="font-size: 0.85rem; padding: 0.3rem 0.9rem;">
                  Sí, eliminar
                </button>
              </form>
            </div>
          </dialog>
        {% endfor %}
      {% else %}
        <p style="color: #666; margin: 0;">Sin parciales registrados.</p>
      {% endif %}

    </div>
  </details>
```

- [ ] **Step 3: Correr suite completa de tests**

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests -v 2
```

Esperado: todos los tests PASS (incluyendo los preexistentes).

- [ ] **Step 4: Commit final**

```
git add docentes/views.py templates/docentes/comision_detail.html
git commit -m "feat(docentes): panel de parciales en comision_detail"
```

---

## Checklist de spec coverage

| Requisito del spec | Task |
|---|---|
| Modelo `Parcial` con comision, nombre, fecha, puntaje_total | Task 1 |
| Modelo `NotaParcial` con puntaje nullable, unique_together | Task 1 |
| Pre-crear `NotaParcial` al crear parcial | Task 5 |
| Admin registrado | Task 3 |
| URL `parcial_create` | Task 5 |
| URL `parcial_edit` | Task 6 |
| URL `parcial_delete` | Task 6 |
| URL `parcial_notas` | Task 7 |
| Formset con guardado en bloque | Task 7 |
| Columna Estudiante: "Apellido, Nombre" o username | Task 7 |
| Ordenado por apellido/nombre/username | Task 7 (qs + modelo) |
| Filas pendientes en amarillo pálido | Task 7 |
| Chips Cargada/Pendiente | Task 7 |
| Encabezado con progreso X/N | Task 7 |
| Panel en `comision_detail` con progreso | Task 8 |
| Botón "Nuevo parcial" | Task 8 |
| Confirmación antes de eliminar | Task 8 |
| Permiso: solo docente de la comisión o staff | Tasks 5, 6, 7, 8 |
