from django.db import migrations, models


def cerrar_instalador_en_sitios_existentes(apps, schema_editor):
    ConfigSitio = apps.get_model('accounts', 'ConfigSitio')
    Usuario = apps.get_model('accounts', 'Usuario')
    if Usuario.objects.filter(is_superuser=True).exists():
        config, _ = ConfigSitio.objects.get_or_create(pk=1)
        config.instalacion_completada = True
        config.save(update_fields=['instalacion_completada'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0020_usuario_research_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='configsitio',
            name='instalacion_completada',
            field=models.BooleanField(
                default=False,
                help_text='Se activa al finalizar el asistente inicial y evita que vuelva a abrirse.',
                verbose_name='instalación inicial completada',
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='idioma_predeterminado',
            field=models.CharField(
                choices=[
                    ('es', 'Castellano'),
                    ('en', 'English'),
                    ('fr', 'Français'),
                    ('de', 'Deutsch'),
                ],
                default='es',
                help_text=(
                    'Idioma que verá quien todavía no haya elegido uno. Cada persona '
                    'puede cambiarlo luego desde el selector del sitio.'
                ),
                max_length=2,
                verbose_name='idioma predeterminado',
            ),
        ),
        migrations.RunPython(
            cerrar_instalador_en_sitios_existentes,
            migrations.RunPython.noop,
        ),
    ]
