"""Agrega campos de umbral en ConfigSitio para las métricas analíticas:
- umbral_convergencia_min_estudiantes (Métrica 3)
- umbral_adivinacion_intentos (Métrica 6)
- umbral_adivinacion_segundos (Métrica 6)
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_colapsar_respuestas_otras_en_un_solo_campo'),
    ]

    operations = [
        migrations.AddField(
            model_name='configsitio',
            name='umbral_convergencia_min_estudiantes',
            field=models.PositiveSmallIntegerField(
                default=5,
                verbose_name='mínimo de estudiantes para curva de convergencia',
                help_text=(
                    'Mínimo de estudiantes que deben haber intentado un ejercicio para '
                    'mostrar su curva de convergencia en el detalle de ejercicio. '
                    'Valor recomendado: 5.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='umbral_adivinacion_intentos',
            field=models.PositiveSmallIntegerField(
                default=5,
                verbose_name='mínimo de intentos para señal de baja variación',
                help_text=(
                    'Cantidad mínima de intentos en el mismo ejercicio para activar '
                    'la señal de "práctica con baja variación entre intentos". '
                    'Valor recomendado: 5.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='umbral_adivinacion_segundos',
            field=models.PositiveSmallIntegerField(
                default=30,
                verbose_name='intervalo máximo (segundos) para señal de baja variación',
                help_text=(
                    'Intervalo promedio entre intentos (en segundos) por debajo del '
                    'cual se activa la señal de "práctica con baja variación entre '
                    'intentos". Valor recomendado: 30.'
                ),
            ),
        ),
    ]
