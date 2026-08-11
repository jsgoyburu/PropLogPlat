"""Formularios del panel docente.

ModelForms para CRUD básico de comisiones, prácticas y ejercicios.
Los querysets se restringen según rol para evitar referencias cruzadas
entre comisiones no gestionadas por el docente autenticado.
"""

import json

from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.db.models import Q

from cursos.models import Cohorte, Comision, NotaParcial, Parcial
from ejercicios.models import Ejercicio, EjercicioPractica, Practica, PracticaComision
from motor import parsear
from motor.parser import normalizar_simbolos


Usuario = get_user_model()


class CohorteForm(forms.ModelForm):
    """Alta de cohorte. Solo la usan superusuarios."""

    class Meta:
        model = Cohorte
        fields = ['anio', 'cuatrimestre']

    def clean(self):
        cleaned = super().clean()
        anio = cleaned.get('anio')
        cuatrimestre = cleaned.get('cuatrimestre')
        if anio and cuatrimestre:
            if Cohorte.objects.filter(anio=anio, cuatrimestre=cuatrimestre).exists():
                raise forms.ValidationError(
                    f'La cohorte {anio} – C{cuatrimestre} ya existe.'
                )
        return cleaned


class ComisionForm(forms.ModelForm):
    """Formulario de creación/edición de comisiones."""

    class Meta:
        model = Comision
        fields = ['nombre', 'tipo_encuesta']


class DocenteComisionForm(forms.Form):
    """Formulario para agregar un docente a una comisión."""

    docente = forms.ModelChoiceField(
        queryset=Usuario.objects.filter(es_docente=True).order_by('username'),
        label='Docente',
        empty_label='— seleccioná un docente —',
    )


class PracticaForm(forms.ModelForm):
    """Formulario para los datos canónicos de una práctica (título, descripción, visibilidad)."""

    class Meta:
        model = Practica
        fields = ['titulo', 'descripcion', 'es_publica']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['es_publica'].label = 'Agregar al banco común (visible para todos los docentes)'


class PracticaComisionForm(forms.ModelForm):
    """Formulario para los datos de contexto de una práctica en una comisión específica."""

    class Meta:
        model = PracticaComision
        fields = ['comision', 'orden', 'fecha_apertura', 'fecha_cierre', 'desbloqueo_secuencial']
        widgets = {
            'fecha_apertura': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'fecha_cierre': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario and not usuario.is_staff:
            self.fields['comision'].queryset = Comision.objects.filter(docentes=usuario)
        self.fields['fecha_apertura'].required = False
        self.fields['fecha_cierre'].required = False
        self.fields['desbloqueo_secuencial'].label = (
            'Desbloqueo secuencial: cada ejercicio se habilita al resolver el anterior'
        )
        self.fields['desbloqueo_secuencial'].help_text = (
            'Desmarcá esta opción para que todos los ejercicios estén disponibles desde el inicio.'
        )
        # Pre-formatear los valores iniciales para el widget datetime-local
        for field_name in ('fecha_apertura', 'fecha_cierre'):
            if self.instance and self.instance.pk:
                valor = getattr(self.instance, field_name)
                if valor:
                    from django.utils import timezone
                    valor_local = timezone.localtime(valor)
                    self.initial[field_name] = valor_local.strftime('%Y-%m-%dT%H:%M')

    def clean(self):
        cleaned_data = super().clean()
        apertura = cleaned_data.get('fecha_apertura')
        cierre = cleaned_data.get('fecha_cierre')
        if apertura and cierre and cierre <= apertura:
            self.add_error('fecha_cierre', 'La fecha de cierre debe ser posterior a la de apertura.')
        return cleaned_data


class EjercicioForm(forms.ModelForm):
    """Formulario de creación/edición de ejercicios."""

    class Meta:
        model = Ejercicio
        fields = ['enunciado', 'formula_solucion', 'tipo', 'es_publico']

    def clean(self):
        """Valida la fórmula solución según el tipo de ejercicio.

        Para ``formalizacion``: valida que sea una FBF y normaliza símbolos.
        Para ``tabla_verdad``: valida que sea JSON con estructura de argumento
        (lista de enunciados, exactamente una conclusión, todas las fórmulas FBF).
        Para ``determinacion_verdad``: valida que sea una FBF; la fórmula
        solución es una fórmula simple (se valida igual que formalización).
        Los valores de verdad del diccionario se manejan en la view.
        """
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        formula = cleaned_data.get('formula_solucion', '')

        if tipo == 'formalizacion':
            formula_normalizada = normalizar_simbolos(formula).strip()
            try:
                parsear(formula_normalizada)
            except ValueError as error:
                self.add_error(
                    'formula_solucion',
                    f'La fórmula solución no es una fórmula bien formada (fbf). ({error})',
                )
            else:
                cleaned_data['formula_solucion'] = formula_normalizada

        elif tipo == 'tabla_verdad':
            # formula_solucion debe ser JSON de argumento (lo envía el frontend)
            try:
                enunciados = json.loads(formula)
            except (json.JSONDecodeError, TypeError):
                self.add_error('formula_solucion', 'El argumento no tiene formato válido.')
                return cleaned_data

            if not isinstance(enunciados, list) or len(enunciados) < 2:
                self.add_error(
                    'formula_solucion',
                    'El argumento debe tener al menos dos proposiciones (premisa y conclusión).',
                )
                return cleaned_data

            conclusiones = [e for e in enunciados if e.get('tipo') == 'conclusion']
            if len(conclusiones) != 1:
                self.add_error(
                    'formula_solucion',
                    'El argumento debe tener exactamente una conclusión.',
                )
                return cleaned_data

            enunciados_normalizados = []
            for e in enunciados:
                formula_e = normalizar_simbolos(e.get('formula', '')).strip()
                try:
                    parsear(formula_e)
                except ValueError as error:
                    self.add_error(
                        'formula_solucion',
                        f'La fórmula "{formula_e}" no es una fórmula bien formada (fbf). ({error})',
                    )
                    return cleaned_data
                enunciados_normalizados.append({'formula': formula_e, 'tipo': e.get('tipo', 'premisa')})

            cleaned_data['formula_solucion'] = json.dumps(enunciados_normalizados, ensure_ascii=False)

        elif tipo == 'determinacion_verdad':
            # La fórmula solución es una FBF simple (igual que formalización)
            formula_normalizada = normalizar_simbolos(formula).strip()
            try:
                parsear(formula_normalizada)
            except ValueError as error:
                self.add_error(
                    'formula_solucion',
                    f'La fórmula solución no es una fórmula bien formada (fbf). ({error})',
                )
            else:
                cleaned_data['formula_solucion'] = formula_normalizada

        return cleaned_data


class EjercicioPracticaForm(forms.ModelForm):
    """Formulario para vincular ejercicios a una práctica en orden."""

    class Meta:
        model = EjercicioPractica
        fields = ['practica', 'ejercicio', 'orden']

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['orden'].required = False
        if usuario and not usuario.is_staff:
            # Mismo criterio de escritura que _puede_editar_practica: prácticas
            # de alguna comisión donde el docente enseña, o propias mientras no
            # las use ninguna comisión.
            self.fields['practica'].queryset = Practica.objects.filter(
                Q(practicas_comisiones__comision__docentes=usuario)
                | Q(creada_por=usuario, practicas_comisiones__isnull=True)
            ).distinct()
            self.fields['ejercicio'].queryset = Ejercicio.objects.filter(
                Q(creado_por=usuario) | Q(es_publico=True)
            ).distinct()


class EstudianteCreateForm(forms.ModelForm):
    """Formulario para alta individual de estudiantes."""

    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = ['username', 'email', 'password', 'first_name', 'last_name']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        validate_email(email)
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con este email.')
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.es_docente = False
        usuario.is_staff = False
        usuario.debe_cambiar_password = True
        usuario.set_password(self.cleaned_data['password'])
        if commit:
            usuario.save()
        return usuario


class EstudianteEditForm(forms.ModelForm):
    """Formulario para editar datos básicos de un estudiante ya existente."""

    class Meta:
        model = Usuario
        fields = ['username', 'email', 'first_name', 'last_name']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if email:
            validate_email(email)
            qs = Usuario.objects.filter(email__iexact=email)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Ya existe un usuario con este email.')
        return email


class ImportarEstudiantesForm(forms.Form):
    """Formulario de carga de archivo Excel para alta masiva."""

    archivo = forms.FileField()

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        if not archivo.name.lower().endswith('.xlsx'):
            raise forms.ValidationError('Solo se permiten archivos .xlsx')
        return archivo


class InstalarPaqueteForm(forms.Form):
    """Subida de una práctica o ejercicio portable en ZIP."""

    archivo = forms.FileField(
        label='Paquete ZIP',
        help_text='ZIP generado por PropLogPlat (máximo 5 MB).',
    )

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        if not archivo.name.lower().endswith('.zip'):
            raise forms.ValidationError('El paquete debe ser un archivo .zip.')
        if archivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError('El paquete supera el máximo de 5 MB.')
        return archivo


class ParcialForm(forms.ModelForm):
    """Formulario de creación/edición de parciales (metadatos, sin notas)."""

    class Meta:
        model = Parcial
        fields = ['nombre', 'fecha', 'puntaje_total']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
        }


def get_nota_parcial_formset(extra=0):
    """Devuelve un FormSet class para editar puntajes de NotaParcial.

    Incluye ausente, puntaje (global) y nota_logica_parcial para permitir
    comparación estadística con la serie histórica.
    """
    from django.forms import modelformset_factory
    return modelformset_factory(
        NotaParcial,
        fields=['ausente', 'puntaje', 'nota_logica_parcial'],
        extra=extra,
        can_delete=False,
    )
