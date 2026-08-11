"""Amplía las choices de Intento.error_categoria con la taxonomía completa
de errores de formalización implementada en motor.clasificador.

No modifica el esquema de la tabla (CharField sin CHECK constraint).
"""

from django.db import migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0018_juicio_estudiante'),
    ]

    operations = [
        migrations.AlterField(
            model_name='intento',
            name='error_categoria',
            field=django.db.models.fields.CharField(
                blank=True,
                choices=[
                    ('tautologia', 'Tautología espuria (siempre verdadero)'),
                    ('contradiccion', 'Contradicción (siempre falso)'),
                    ('polaridad', 'Polaridad (negación exacta de la solución)'),
                    ('mas_fuerte', 'Más fuerte: solución implica estudiante, no al revés'),
                    ('mas_debil', 'Más débil: estudiante implica solución, no al revés'),
                    ('equivalente_alt', 'Formalización alternativa válida (revisar)'),
                    ('error_parcial_1', 'Error parcial — 1 fila distinta'),
                    ('error_parcial_2', 'Error parcial — 2 filas distintas'),
                    ('error_sistemico', 'Error sistémico (más de la mitad de filas distintas)'),
                    ('variables_extra', 'Variables extra (más variables que la solución)'),
                    ('variables_menos', 'Variables insuficientes (menos variables que la solución)'),
                    ('sin_clasificar', 'Sin clasificar'),
                    ('juicio', 'Error solo en juicio de validez (tabla correcta, juicio incorrecto)'),
                    ('columna_premisa', 'Error en columna de premisa'),
                    ('columna_conclusion', 'Error en columna de conclusión'),
                    ('error_parse', 'Error de parseo (fórmula no válida)'),
                    ('otro', 'Otro / no clasificado'),
                ],
                default=None,
                help_text=(
                    'Categoría del error lógico. Calculada automáticamente al guardar el '
                    'intento (ejercicios de formalización) o por el management command '
                    'poblar_error_categoria. Null = aún no procesado o intento correcto.'
                ),
                max_length=30,
                null=True,
                verbose_name='categoría de error',
            ),
        ),
    ]
