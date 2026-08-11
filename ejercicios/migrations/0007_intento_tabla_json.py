from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0006_intento_respuesta_raw_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='intento',
            name='tabla_json',
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                verbose_name='tabla de verdad',
                help_text=(
                    'Tabla completada por el estudiante en ejercicios de tabla de verdad. '
                    'Lista de filas: [{"A": true, "B": false, "P1": true, "C": false}, ...].'
                ),
            ),
        ),
    ]
