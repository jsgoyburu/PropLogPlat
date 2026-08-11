from django.db import migrations, models


class Migration(migrations.Migration):
    """Agrega research_id a Usuario para pseudonimización en datasets de investigación.

    El campo es nullable: solo se genera para estudiantes con
    consentimiento_investigacion=True. El comando de management
    ``poblar_research_id`` gestiona la población inicial y las transiciones.
    """

    dependencies = [
        ('accounts', '0019_encuestaestudiante_acertijo_cirugia_correcto'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='research_id',
            field=models.UUIDField(
                null=True,
                blank=True,
                default=None,
                editable=False,
                unique=True,
                verbose_name='ID de investigación',
                help_text=(
                    'Pseudónimo estable para exportación de datos de investigación. '
                    'Se genera al confirmar consentimiento_investigacion=True y se '
                    'anula si el estudiante revoca el consentimiento. '
                    'Nunca se expone en la UI. Permite cruzar datasets '
                    '(encuesta ↔ intentos) sin revelar la identidad del estudiante.'
                ),
            ),
        ),
    ]
