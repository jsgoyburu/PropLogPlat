from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0005_add_practica_es_publica_creada_por'),
    ]

    operations = [
        migrations.AlterField(
            model_name='intento',
            name='respuesta_raw',
            field=models.CharField(
                max_length=2000,
                verbose_name='respuesta',
                help_text='Fórmula enviada por el estudiante en ASCII normalizado, o JSON del argumento para ejercicios de tabla de verdad.',
            ),
        ),
    ]
