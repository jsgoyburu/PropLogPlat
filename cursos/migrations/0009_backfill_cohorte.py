"""Backfill de cohorte: toda la base existente es 2026-C1.

No hay estudiantes de otra camada todavía, así que no hace falta derivar la
cohorte de ninguna fecha. La guarda del principio existe porque esta migración
corre contra producción sobre un supuesto que no es verificable desde el
repositorio: si el supuesto no vale, aborta en vez de etiquetar mal en silencio.

atomic = False porque PostgreSQL no permite ALTER TABLE en la misma transacción
que INSERTs con FK deferred pendientes (mismo motivo que ejercicios/0015).
"""
from django.db import migrations

ANIO = 2026
CUATRIMESTRE = 1


def backfill(apps, schema_editor):
    Cohorte = apps.get_model('cursos', 'Cohorte')
    Inscripcion = apps.get_model('cursos', 'Inscripcion')
    Parcial = apps.get_model('cursos', 'Parcial')
    Progreso = apps.get_model('ejercicios', 'Progreso')
    Intento = apps.get_model('ejercicios', 'Intento')

    fuera = Inscripcion.objects.exclude(fecha_inscripcion__year=ANIO).count()
    if fuera:
        raise RuntimeError(
            f'{fuera} inscripciones fuera de {ANIO}. El backfill asume que toda '
            f'la base es {ANIO}-C{CUATRIMESTRE}. Revisar antes de migrar.'
        )

    cohorte, _ = Cohorte.objects.get_or_create(
        anio=ANIO,
        cuatrimestre=CUATRIMESTRE,
        defaults={'activa': True},
    )

    for modelo in (Inscripcion, Parcial, Progreso, Intento):
        modelo.objects.filter(cohorte__isnull=True).update(cohorte=cohorte)

    # Corte temprano: si algo quedó sin atribuir, fallar acá y no en el NOT NULL.
    for modelo in (Inscripcion, Parcial, Progreso, Intento):
        faltan = modelo.objects.filter(cohorte__isnull=True).count()
        if faltan:
            raise RuntimeError(
                f'{modelo.__name__}: {faltan} filas sin cohorte tras el backfill.'
            )


def revertir(apps, schema_editor):
    for app, nombre in (
        ('cursos', 'Inscripcion'), ('cursos', 'Parcial'),
        ('ejercicios', 'Progreso'), ('ejercicios', 'Intento'),
    ):
        apps.get_model(app, nombre).objects.update(cohorte=None)


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('cursos', '0008_inscripcion_cohorte_parcial_cohorte'),
        ('ejercicios', '0027_intento_cohorte_progreso_cohorte'),
    ]

    operations = [
        migrations.RunPython(backfill, revertir),
    ]
