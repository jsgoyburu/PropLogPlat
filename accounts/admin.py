"""Admin de la app accounts."""

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import ConfigSitio, EncuestaEstudiante, Usuario


class ConfigSitioForm(forms.ModelForm):
    """Form del admin con campo de subida de favicon."""

    favicon_upload = forms.FileField(
        required=False,
        label='Favicon',
        help_text='Subí un archivo .ico, .png o .svg (32×32 px mínimo). '
                  'Dejá vacío para mantener el favicon actual.',
    )

    class Meta:
        model = ConfigSitio
        fields = (
            'nombre_sitio', 'idioma_predeterminado', 'contacto_privacidad', 'color_primario',
            'color_acento', 'favicon_upload',
        )

    def save(self, commit=True):
        import base64
        instance = super().save(commit=False)
        archivo = self.cleaned_data.get('favicon_upload')
        if archivo:
            # Guardar como base64 en TextField (compatible con PostgreSQL text)
            instance.favicon_data = base64.b64encode(archivo.read()).decode('ascii')
            ct = archivo.content_type or ''
            if not ct or ct == 'application/octet-stream':
                name = archivo.name.lower()
                if name.endswith('.ico'):
                    ct = 'image/x-icon'
                elif name.endswith('.png'):
                    ct = 'image/png'
                elif name.endswith('.svg'):
                    ct = 'image/svg+xml'
                else:
                    ct = 'image/x-icon'
            instance.favicon_content_type = ct
        if commit:
            instance.save()
        return instance


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin para el modelo Usuario.

    Extiende UserAdmin de Django para incluir el campo ``es_docente``
    en los fieldsets de edición y en la lista.
    """

    list_display = (
        'username', 'email', 'es_docente', 'is_staff', 'is_active',
        'debe_cambiar_password', 'consentimiento_pedagogico',
        'consentimiento_investigacion', 'encuesta_completada',
    )
    list_filter = (
        'es_docente', 'is_staff', 'is_active',
        'debe_cambiar_password', 'consentimiento_pedagogico',
        'consentimiento_investigacion', 'encuesta_completada',
    )
    search_fields = ('username', 'email', 'first_name', 'last_name')

    fieldsets = UserAdmin.fieldsets + (
        ('Rol en la plataforma', {'fields': ('es_docente', 'debe_cambiar_password')}),
        ('Consentimientos informados', {
            'fields': (
                'consentimiento_pedagogico',
                'consentimiento_investigacion',
                'consentimiento_contacto_seguimiento',
                'fecha_consentimiento',
                'encuesta_completada',
            ),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Rol en la plataforma', {'fields': ('es_docente', 'debe_cambiar_password')}),
    )


@admin.register(ConfigSitio)
class ConfigSitioAdmin(admin.ModelAdmin):
    """Admin singleton para la configuración del sitio.

    Siempre redirige a editar la fila única (pk=1) en lugar de mostrar
    el listado. No permite agregar ni borrar instancias.
    """

    form = ConfigSitioForm
    fields = (
        'nombre_sitio', 'idioma_predeterminado', 'contacto_privacidad', 'color_primario',
        'color_acento', 'favicon_upload', 'error_consenso_min',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        from django.shortcuts import redirect
        from django.urls import path

        urls = super().get_urls()

        def redirect_to_edit(req):
            ConfigSitio.get()  # asegura que existe la fila
            return redirect('admin:accounts_configsitio_change', 1)

        extra = [
            path('', self.admin_site.admin_view(redirect_to_edit), name='configsitio_redirect'),
        ]
        return extra + urls


@admin.register(EncuestaEstudiante)
class EncuestaEstudianteAdmin(admin.ModelAdmin):
    """Admin de encuestas socioeducativas.

    Muestra datos identificables; acceso restringido a is_staff=True.
    Para analíticas de investigación, filtrar siempre por
    estudiante__consentimiento_investigacion=True.
    """

    list_display = (
        'estudiante', 'facultad', 'carrera',
        'situacion_laboral', 'estudios_superiores',
    )
    list_filter = (
        'facultad', 'situacion_laboral', 'estudios_superiores',
        'tiempo_en_cbc', 'tipo_escuela',
    )
    search_fields = (
        'estudiante__username', 'estudiante__first_name',
        'estudiante__last_name', 'dni',
    )
    readonly_fields = ('estudiante',)
