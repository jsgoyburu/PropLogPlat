from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0022_configsitio_nombre_proplogplat'),
    ]

    operations = [
        migrations.AddField(
            model_name='configsitio',
            name='contacto_privacidad',
            field=models.EmailField(
                blank=True,
                default='',
                help_text=(
                    'Contacto responsable para ejercer derechos sobre datos personales. '
                    'Si queda vacío, los consentimientos remiten al equipo docente local.'
                ),
                max_length=254,
                verbose_name='correo de privacidad',
            ),
        ),
    ]
