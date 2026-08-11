"""Admin de la app cursos."""

from django.contrib import admin

from cursos.models import Cohorte, Comision, Inscripcion, NotaParcial, Parcial


class InscripcionInline(admin.TabularInline):
    """Inline para ver estudiantes inscriptos desde la comisión."""

    model = Inscripcion
    extra = 0
    autocomplete_fields = ['estudiante']


class NotaParcialInline(admin.TabularInline):
    model = NotaParcial
    extra = 0
    fields = ('estudiante', 'ausente', 'puntaje', 'nota_logica_parcial')
    readonly_fields = ('estudiante',)


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
    list_display = ('estudiante', 'parcial', 'ausente', 'puntaje', 'nota_logica_parcial')
    list_filter = ('parcial__comision', 'parcial', 'ausente')
    search_fields = ('estudiante__username', 'estudiante__last_name')


@admin.register(Cohorte)
class CohorteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'anio', 'cuatrimestre', 'activa')
    list_filter = ('anio', 'cuatrimestre', 'activa')
    ordering = ('-anio', '-cuatrimestre')
