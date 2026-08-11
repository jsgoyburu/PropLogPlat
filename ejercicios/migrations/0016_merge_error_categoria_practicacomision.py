from django.db import migrations


class Migration(migrations.Migration):
    """Merge migration: resuelve la bifurcación entre
    0014_intento_error_categoria y 0015_practicacomision."""

    dependencies = [
        ('ejercicios', '0014_intento_error_categoria'),
        ('ejercicios', '0015_practicacomision'),
    ]

    operations = []
