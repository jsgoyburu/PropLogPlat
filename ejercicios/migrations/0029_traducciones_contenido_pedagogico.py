from django.db import migrations, models
import django_ckeditor_5.fields


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0028_cohorte_not_null'),
    ]

    operations = [
        migrations.AddField(
            model_name='ejercicio',
            name='enunciado_de',
            field=models.TextField(blank=True, default='', help_text='Traducción opcional. Si queda vacía se mostrará el castellano original.', verbose_name='enunciado en alemán'),
        ),
        migrations.AddField(
            model_name='ejercicio',
            name='enunciado_en',
            field=models.TextField(blank=True, default='', help_text='Traducción opcional. Si queda vacía se mostrará el castellano original.', verbose_name='enunciado en inglés'),
        ),
        migrations.AddField(
            model_name='ejercicio',
            name='enunciado_fr',
            field=models.TextField(blank=True, default='', help_text='Traducción opcional. Si queda vacía se mostrará el castellano original.', verbose_name='enunciado en francés'),
        ),
        migrations.AddField(
            model_name='practica',
            name='descripcion_de',
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name='extends', null=True, verbose_name='descripción en alemán'),
        ),
        migrations.AddField(
            model_name='practica',
            name='descripcion_en',
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name='extends', null=True, verbose_name='descripción en inglés'),
        ),
        migrations.AddField(
            model_name='practica',
            name='descripcion_fr',
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name='extends', null=True, verbose_name='descripción en francés'),
        ),
        migrations.AddField(
            model_name='practica',
            name='titulo_de',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='título en alemán'),
        ),
        migrations.AddField(
            model_name='practica',
            name='titulo_en',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='título en inglés'),
        ),
        migrations.AddField(
            model_name='practica',
            name='titulo_fr',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='título en francés'),
        ),
    ]
