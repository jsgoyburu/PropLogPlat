from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_configsitio_metricas_analiticas'),
    ]

    operations = [
        migrations.AddField(
            model_name='configsitio',
            name='pistas_ia_activas',
            field=models.BooleanField(
                default=True,
                verbose_name='pistas pedagógicas con IA activas',
                help_text=(
                    'Si está desactivado, no se generan pistas automáticas con Gemini/Groq '
                    'al resolver ejercicios. Útil para controlar el consumo de tokens.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='revision_diccionario_activa',
            field=models.BooleanField(
                default=True,
                verbose_name='revisión de diccionarios con IA activa',
                help_text=(
                    'Si está desactivado, no se envía el diccionario estudiantil a Groq '
                    'para su revisión automática. Útil para controlar el consumo de tokens.'
                ),
            ),
        ),
    ]
