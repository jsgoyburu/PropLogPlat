from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0019_update_error_categoria_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='intento',
            name='revision_diccionario',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Sin revisar (no aplica o Groq no disponible)'),
                    ('pasa', 'Pasa — Groq aprobó el diccionario'),
                    ('revisar', 'Revisar — Groq sugiere revisión docente'),
                ],
                default='',
                max_length=10,
                verbose_name='revisión del diccionario',
                help_text=(
                    'Resultado de la revisión automática del diccionario por Groq (solo intentos '
                    'correctos con diccionario). Vacío = no aplica o Groq no disponible.'
                ),
            ),
        ),
    ]
