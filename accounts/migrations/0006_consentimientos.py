from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_error_consenso_min'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='consentimiento_pedagogico',
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text=(
                    'El usuario acepta que sus datos, con información identificable, '
                    'sean utilizados por sus docentes con fines pedagógicos. '
                    'None = aún no respondió; True = aceptó; False = no aceptó.'
                ),
                null=True,
                verbose_name='consentimiento pedagógico',
            ),
        ),
        migrations.AddField(
            model_name='usuario',
            name='consentimiento_investigacion',
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text=(
                    'El usuario acepta que sus datos, debidamente anonimizados, '
                    'sean utilizados con fines académicos y de investigación. '
                    'None = aún no respondió; True = aceptó; False = no aceptó.'
                ),
                null=True,
                verbose_name='consentimiento de investigación',
            ),
        ),
        migrations.AddField(
            model_name='usuario',
            name='fecha_consentimiento',
            field=models.DateTimeField(
                blank=True,
                help_text='Fecha y hora en que el usuario respondió los consentimientos.',
                null=True,
                verbose_name='fecha de consentimiento',
            ),
        ),
    ]
