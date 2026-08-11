from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_configsitio_ia_toggles'),
    ]

    operations = [
        migrations.AddField(
            model_name='encuestaestudiante',
            name='acertijo_cirugia_correcto',
            field=models.BooleanField(
                blank=True,
                null=True,
                verbose_name='acertijo cirugía: correcto (evaluado por IA)',
            ),
        ),
    ]
