from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0021_alter_intento_error_categoria'),
    ]

    operations = [
        migrations.AddField(
            model_name='practicacomision',
            name='desbloqueo_secuencial',
            field=models.BooleanField(default=True, help_text='Si está marcado, cada ejercicio se habilita al resolver correctamente el anterior. Si no, todos los ejercicios están disponibles desde el inicio.', verbose_name='desbloqueo secuencial'),
        ),
    ]
