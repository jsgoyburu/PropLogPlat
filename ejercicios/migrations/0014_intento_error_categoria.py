from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0013_practica_origen'),
    ]

    operations = [
        migrations.AddField(
            model_name='intento',
            name='error_categoria',
            field=models.CharField(
                blank=True,
                choices=[
                    ('polaridad', 'Error de polaridad (negación total de la solución)'),
                    ('tautologia', 'Tautología espuria (siempre verdadero)'),
                    ('contradiccion', 'Contradicción (siempre falso)'),
                    ('parcial', 'Error parcial (algunas filas coinciden con la solución)'),
                    ('juicio', 'Error solo en juicio de validez (tabla correcta, juicio incorrecto)'),
                    ('columna_premisa', 'Error en columna de premisa (tabla de verdad)'),
                    ('columna_conclusion', 'Error en columna de conclusión (tabla de verdad)'),
                    ('error_parse', 'Error de parseo (fórmula no válida)'),
                    ('otro', 'Otro / no clasificado'),
                ],
                default=None,
                help_text=(
                    'Categoría del error lógico. Calculada offline por el management command '
                    'calcular_categorias_error. Null = aún no procesado o intento correcto.'
                ),
                max_length=30,
                null=True,
                verbose_name='categoría de error',
            ),
        ),
    ]
