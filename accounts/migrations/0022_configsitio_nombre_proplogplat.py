from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0021_configsitio_idioma_predeterminado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configsitio',
            name='nombre_sitio',
            field=models.CharField(
                default='PropLogPlat',
                max_length=100,
                verbose_name='nombre del sitio',
            ),
        ),
    ]
