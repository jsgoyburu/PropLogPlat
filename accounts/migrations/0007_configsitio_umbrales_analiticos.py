"""Agrega los 5 umbrales analíticos a ConfigSitio.

Estos campos reemplazan las constantes _MIN_INTENTOS, _RIESGO_UMBRAL,
_SILENCIO_UMBRAL, _MARATON_UMBRAL y _ARRANQUE_DIAS que estaban
hardcodeadas en analiticas/views.py.

Motivación (AGENTS.md §8 — Transparencia y legibilidad):
    Las decisiones algorítmicas deben ser explícitas y auditables.
    Un docente no puede calibrar un criterio que no conoce.
    Al moverlos a ConfigSitio, el criterio es editable y visible
    desde el admin, y queda documentado con su propio help_text.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_consentimientos'),
    ]

    operations = [
        migrations.AddField(
            model_name='configsitio',
            name='umbral_min_intentos',
            field=models.PositiveSmallIntegerField(
                default=3,
                verbose_name='mínimo de intentos para ejercicio difícil',
                help_text=(
                    'Un ejercicio aparece en el panel "Ejercicios difíciles" solo si '
                    'acumuló al menos este número de intentos totales (evita ruido con '
                    'ejercicios poco intentados). Valor recomendado: 3.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='umbral_riesgo',
            field=models.PositiveSmallIntegerField(
                default=5,
                verbose_name='umbral de racha de fallos (alerta de acompañamiento)',
                help_text=(
                    'Cantidad de intentos incorrectos consecutivos en un mismo ejercicio '
                    'a partir de la cual un estudiante aparece en el panel de alertas de '
                    'acompañamiento. Valor recomendado: 5.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='umbral_silencio_dias',
            field=models.PositiveSmallIntegerField(
                default=7,
                verbose_name='días de silencio para alerta visual',
                help_text=(
                    'Días sin actividad a partir de los cuales un estudiante recibe '
                    'resaltado visual en el panel de seguimiento. Valor recomendado: 7.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='umbral_maraton',
            field=models.PositiveSmallIntegerField(
                default=6,
                verbose_name='umbral de concentración de práctica (ratio intentos/días)',
                help_text=(
                    'Ratio intentos/días de actividad a partir del cual se considera '
                    'que el estudiante concentró la práctica en muy pocos días. '
                    'Valor recomendado: 6.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='umbral_arranque_dias',
            field=models.PositiveSmallIntegerField(
                default=14,
                verbose_name='ventana de arranque temprano (días)',
                help_text=(
                    'Cantidad de días desde la apertura de una práctica durante los '
                    'cuales se espera que el estudiante haya iniciado. Quienes no '
                    'realizaron ningún intento en ese período aparecen en el panel '
                    'de arranque tardío. Valor recomendado: 14.'
                ),
            ),
        ),
    ]
