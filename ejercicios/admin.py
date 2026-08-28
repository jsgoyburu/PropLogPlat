"""Admin de la app ejercicios."""

from django.contrib import admin

from ejercicios.models import (
    Ejercicio, EjercicioPractica, Intento, Practica, PracticaComision, Progreso,
)


class EjercicioPracticaInline(admin.TabularInline):
    """Inline para gestionar el orden de ejercicios dentro de una práctica."""

    model = EjercicioPractica
    extra = 1
    autocomplete_fields = ['ejercicio']
    ordering = ['orden']


class PracticaComisionInline(admin.TabularInline):
    """Inline para ver/editar las comisiones a las que está asignada la práctica."""

    model = PracticaComision
    extra = 0
    ordering = ['comision', 'orden']


@admin.register(Ejercicio)
class EjercicioAdmin(admin.ModelAdmin):
    """Admin para el banco de ejercicios."""

    list_display = ('__str__', 'tipo', 'es_publico', 'creado_por', 'fecha_creacion')
    list_filter = ('tipo', 'es_publico')
    search_fields = ('enunciado', 'formula_solucion')
    readonly_fields = ('fecha_creacion',)
    fieldsets = (
        ('Original en castellano', {
            'fields': ('enunciado', 'formula_solucion', 'tipo', 'es_publico'),
        }),
        ('Traducciones opcionales', {
            'fields': (
                'enunciado_en', 'enunciado_fr', 'enunciado_de',
                'enunciado_zh_hans',
            ),
            'description': 'Si una traducción queda vacía, el sitio muestra el castellano original.',
        }),
        ('Metadatos', {'fields': ('creado_por', 'fecha_creacion')}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(Practica)
class PracticaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'es_publica', 'creada_por')
    list_filter = ('es_publica',)
    search_fields = ('titulo',)
    inlines = [EjercicioPracticaInline, PracticaComisionInline]
    fieldsets = (
        ('Original en castellano', {
            'fields': ('titulo', 'descripcion', 'es_publica', 'creada_por', 'practica_origen'),
        }),
        ('English', {'fields': ('titulo_en', 'descripcion_en')}),
        ('Français', {'fields': ('titulo_fr', 'descripcion_fr')}),
        ('Deutsch', {'fields': ('titulo_de', 'descripcion_de')}),
        ('简体中文', {'fields': ('titulo_zh_hans', 'descripcion_zh_hans')}),
    )


@admin.register(PracticaComision)
class PracticaComisionAdmin(admin.ModelAdmin):
    list_display = ('practica', 'comision', 'orden', 'fecha_apertura', 'fecha_cierre')
    list_filter = ('comision',)
    search_fields = ('practica__titulo', 'comision__nombre')


@admin.register(Intento)
class IntentoAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'ejercicio_practica', 'es_correcto', 'tiene_comentario', 'timestamp')
    list_filter = ('es_correcto', 'practica_comision__comision')
    search_fields = ('estudiante__username', 'respuesta_raw', 'comentario_docente')
    readonly_fields = ('timestamp',)
    fields = (
        'estudiante',
        'ejercicio_practica',
        'practica_comision',
        'respuesta_raw',
        'es_correcto',
        'comentario_docente',
        'timestamp',
    )

    @admin.display(boolean=True, description='comentado')
    def tiene_comentario(self, obj):
        return bool((obj.comentario_docente or '').strip())


@admin.register(Progreso)
class ProgresoAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'practica_comision', 'ejercicio_practica_actual')
    list_filter = ('practica_comision__comision',)
    search_fields = ('estudiante__username',)
