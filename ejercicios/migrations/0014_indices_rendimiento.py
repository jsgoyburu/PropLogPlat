"""Agrega índices de rendimiento en Intento y Practica.

- Intento: (es_correcto, aprobado_docente) para la cola de correcciones pendientes.
- Intento: (aprobado_docente) para analíticas y filtros de aprobación.
- Practica: (practica_origen) para el filtro del banco de prácticas
  (_get_practicas_disponibles usa practica_origen__isnull=True).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0013_practica_origen'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='intento',
            index=models.Index(
                fields=['es_correcto', 'aprobado_docente'],
                name='intento_correcto_aprobado_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='intento',
            index=models.Index(
                fields=['aprobado_docente'],
                name='intento_aprobado_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='practica',
            index=models.Index(
                fields=['practica_origen'],
                name='practica_origen_idx',
            ),
        ),
    ]
