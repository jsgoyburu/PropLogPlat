"""Agrega campos de favicon a ConfigSitio.

El favicon se almacena codificado en base64 dentro de un TextField,
compatible con SQLite y PostgreSQL sin problemas de tipo de columna.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_configsitio'),
    ]

    operations = [
        migrations.AddField(
            model_name='configsitio',
            name='favicon_data',
            field=models.TextField(
                blank=True,
                null=True,
                verbose_name='favicon (datos, base64)',
            ),
        ),
        migrations.AddField(
            model_name='configsitio',
            name='favicon_content_type',
            field=models.CharField(
                blank=True,
                default='',
                max_length=50,
                verbose_name='favicon content-type',
            ),
        ),
    ]
