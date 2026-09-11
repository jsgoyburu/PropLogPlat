"""Espacio libre: verificación formal sin registrar actividad académica."""

from itertools import product

from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_http_methods
from sympy import Symbol

from motor.parser import extraer_variables_en_orden, parsear, validar_parentesis_en_operaciones_mixtas
from motor.tabla import generar_tabla_desde_expr


class FormulaLibreForm(forms.Form):
    formula = forms.CharField(max_length=500, label=gettext_lazy("Fórmula"), widget=forms.Textarea(attrs={
        'rows': 3, 'spellcheck': 'false', 'aria-describedby': 'formula-ayuda',
    }))

    def clean_formula(self):
        formula = self.cleaned_data['formula']
        try:
            variables = extraer_variables_en_orden(formula)
            # Acotar antes de parsear/evaluar: 256 filas como máximo.
            if len(variables) > 8:
                raise forms.ValidationError(_("Usá hasta 8 variables por fórmula (256 filas)."))
            self.expr = parsear(formula)
            validar_parentesis_en_operaciones_mixtas(formula)
        except ValueError as exc:
            self.obf = False
            raise forms.ValidationError(str(exc)) from exc
        except RecursionError as exc:
            raise forms.ValidationError(_("La fórmula tiene demasiados niveles de anidación.")) from exc
        self.variables = variables
        return formula


class ArgumentoLibreForm(forms.Form):
    premisas = forms.CharField(max_length=4000, label=gettext_lazy('Premisas'),
                              widget=forms.Textarea(attrs={'rows': 4, 'spellcheck': 'false'}))
    conclusion = forms.CharField(max_length=500, label=gettext_lazy('Conclusión'),
                                widget=forms.Textarea(attrs={'rows': 2, 'spellcheck': 'false'}))

    def clean(self):
        data = super().clean()
        if not all(data.get(field) for field in ('premisas', 'conclusion')):
            return data
        premisas = [line.strip() for line in data['premisas'].splitlines() if line.strip()]
        if len(premisas) > 8:
            self.add_error('premisas', _('Ingresá entre 1 y 8 premisas, una por línea.'))
            return data
        self.formulas = premisas + [data['conclusion']]
        self.expresiones = []
        self.variables = []
        for index, formula in enumerate(self.formulas):
            subform = FormulaLibreForm({'formula': formula})
            field = 'premisas' if index < len(premisas) else 'conclusion'
            if not subform.is_valid():
                label = _('Premisa %(numero)s') % {'numero': index + 1} if field == 'premisas' else _('Conclusión')
                for error in subform.errors['formula']:
                    self.add_error(field, f'{label}: {error}')
                continue
            self.expresiones.append(subform.expr)
            self.variables.extend(v for v in subform.variables if v not in self.variables)
        if len(self.variables) > 8:
            self.add_error(None, _('Usá hasta 8 variables en todo el argumento (256 filas).'))
        return data


def analizar_argumento(form):
    """Contradicción de premisas y prueba de validez por P1 ∧ … ∧ Pn ∧ ¬C.

    Evalúa todas las fórmulas sobre las mismas asignaciones. No compara
    formalizaciones ni renombra variables: aquí no hay una solución modelo.
    """
    symbols = [Symbol(v) for v in form.variables]
    tablas = [generar_tabla_desde_expr(expr, symbols) for expr in form.expresiones]
    filas = []
    compatibles = False
    contraejemplos = 0
    for index, values in enumerate(product([True, False], repeat=len(symbols))):
        resultados = [tabla[index]['resultado'] for tabla in tablas]
        premisas_v = all(resultados[:-1])
        contraejemplo = premisas_v and not resultados[-1]
        compatibles |= premisas_v
        contraejemplos += int(contraejemplo)
        filas.append({'valores': list(values) + resultados + [not resultados[-1], contraejemplo],
                      'contraejemplo': contraejemplo})
    return {'filas': filas, 'variables': form.variables,
            'premisas': form.formulas[:-1], 'conclusion': form.formulas[-1],
            'contradiccion_premisas': not compatibles,
            'contradiccion_prueba': contraejemplos == 0,
            'contraejemplos': contraejemplos}


@login_required
@require_http_methods(['GET', 'POST'])
def experimentacion(request):
    """Disponible para cualquier cuenta, sin inscripción ni cambios de progreso."""
    modo = (request.POST if request.method == 'POST' else request.GET).get('modo', 'formula')
    es_argumento = modo == 'argumento'
    form_class = ArgumentoLibreForm if es_argumento else FormulaLibreForm
    form = form_class(request.POST if request.method == 'POST' else None)
    context = {'form': form, 'es_argumento': es_argumento}
    if request.method == 'POST' and form.is_valid():
        if es_argumento:
            context['argumento'] = analizar_argumento(form)
            return render(request, 'ejercicios/experimentacion.html', context)
        context['valida'] = True
        if request.POST.get('accion') == 'tabla':
            # Una columna por variable escrita, incluso si SymPy la simplifica.
            # Generar cada asignación por posición evita colisionar con una
            # variable legítima llamada «resultado» en los dicts del motor.
            symbols = [Symbol(name) for name in form.variables]
            tabla = generar_tabla_desde_expr(form.expr, symbols)
            context['filas'] = [list(values) + [row['resultado']]
                                for values, row in zip(product([True, False], repeat=len(symbols)), tabla)]
            context['variables'] = form.variables
            resultados = [row['resultado'] for row in tabla]
            context['clasificacion'] = (_('Tautología') if all(resultados) else
                                        _('Contradicción') if not any(resultados) else _('Contingencia'))
    context['no_obf'] = getattr(form, 'obf', None) is False
    return render(request, 'ejercicios/experimentacion.html', context)
