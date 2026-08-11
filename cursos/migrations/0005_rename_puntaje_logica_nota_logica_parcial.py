from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cursos', '0004_notaparcial_ausente_logica_parcial_umbrales'),
    ]

    operations = [
        migrations.RenameField(
            model_name='notaparcial',
            old_name='puntaje_logica',
            new_name='nota_logica_parcial',
        ),
    ]
