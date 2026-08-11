"""Backfill de la atribución por comisión.

Primero atribuye los Intento con practica_comision en NULL, porque el backfill
de Progreso reconstruye punteros a partir de esos intentos y necesita que estén
ya atribuidos. Las reglas viven en ejercicios/backfill.py.
"""

from django.db import migrations

from ejercicios.backfill import (
    atribuir_progreso,
    construir_indices,
    pc_para_intento,
    pcs_candidatos,
    reatribuir_intento,
)


def _backfill_intentos(apps, schema_editor):
    Intento = apps.get_model('ejercicios', 'Intento')
    PracticaComision = apps.get_model('ejercicios', 'PracticaComision')
    Inscripcion = apps.get_model('cursos', 'Inscripcion')

    pcs_por_practica, comisiones_por_estudiante = construir_indices(
        PracticaComision, Inscripcion,
    )

    atribuidos = 0
    sin_atribuir = 0
    for intento in Intento.objects.filter(practica_comision__isnull=True).select_related(
        'ejercicio_practica'
    ):
        pc_id = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            intento.ejercicio_practica.practica_id, intento.estudiante_id,
        )
        if pc_id is None:
            sin_atribuir += 1
            continue
        intento.practica_comision_id = pc_id
        intento.save(update_fields=['practica_comision'])
        atribuidos += 1

    # Reconciliar los que YA tienen pc: la 0015 los pobló con un mapa global
    # practica_id -> pc, quedándose con un pc arbitrario por práctica y sin
    # mirar la inscripción del estudiante. Ver reatribuir_intento().
    reatribuidos = 0
    for intento in Intento.objects.filter(practica_comision__isnull=False).select_related(
        'ejercicio_practica'
    ):
        pc_id = reatribuir_intento(
            pcs_por_practica, comisiones_por_estudiante,
            intento.ejercicio_practica.practica_id, intento.estudiante_id,
            intento.practica_comision_id,
        )
        if pc_id is None:
            continue
        intento.practica_comision_id = pc_id
        intento.save(update_fields=['practica_comision'])
        reatribuidos += 1

    print(
        f'  Intento: {atribuidos} atribuidos, {sin_atribuir} sin atribuir, '
        f'{reatribuidos} reatribuidos'
    )

    # La 0026 vuelve Intento.practica_comision NOT NULL. Si acá quedó alguno sin
    # atribuir, esa migración moriría con un IntegrityError opaco y con Progreso
    # ya re-clavado por la 0025. Cortamos antes, con un mensaje accionable.
    #
    # Un intento queda sin atribuir cuando su estudiante no tiene inscripción en
    # ninguna comisión que tenga asignada esa práctica: típicamente, alguien
    # desinscripto después de haber intentado.
    #
    # Verificado el 2026-08-08 contra producción: 0 de 3140 intentos en NULL,
    # así que esta guarda no se dispara ahí.
    if sin_atribuir:
        raise RuntimeError(
            f'{sin_atribuir} Intento no se pudieron atribuir a ninguna '
            'PracticaComision: su estudiante no está inscripto en ninguna comisión '
            'que tenga asignada esa práctica.\n'
            'La migración 0026 los rechazaría al volver la columna NOT NULL.\n'
            'Resolvé antes: reinscribí a esos estudiantes, asigná la práctica a su '
            'comisión, o borrá esos intentos huérfanos si ya no corresponden.\n'
            'Para listarlos:\n'
            '  SELECT i.id, i.estudiante_id, ep.practica_id\n'
            '  FROM ejercicios_intento i\n'
            '  JOIN ejercicios_ejerciciopractica ep ON ep.id = i.ejercicio_practica_id\n'
            '  WHERE i.practica_comision_id IS NULL;'
        )


def _backfill_progresos(apps, schema_editor):
    Progreso = apps.get_model('ejercicios', 'Progreso')
    EjercicioPractica = apps.get_model('ejercicios', 'EjercicioPractica')
    Intento = apps.get_model('ejercicios', 'Intento')
    PracticaComision = apps.get_model('ejercicios', 'PracticaComision')
    Inscripcion = apps.get_model('cursos', 'Inscripcion')

    pcs_por_practica, comisiones_por_estudiante = construir_indices(
        PracticaComision, Inscripcion,
    )

    conteos = {'n1': 0, 'n0': 0, 'n2': 0}
    # Solo las filas todavía sin resolver: re-correr esta migración después de
    # un deploy parcial no debe volver a partir filas ya atribuidas (violaría
    # el unique_together nuevo) ni reprocesarlas de más.
    for progreso in Progreso.objects.filter(practica_comision__isnull=True):
        candidatos = pcs_candidatos(
            pcs_por_practica, comisiones_por_estudiante,
            progreso.practica_id, progreso.estudiante_id,
        )
        resultado = atribuir_progreso(
            Progreso, EjercicioPractica, Intento, progreso, candidatos,
        )
        conteos[resultado] += 1

    print(
        f"  Progreso: {conteos['n1']} inequivocos, {conteos['n0']} huerfanos "
        f"borrados, {conteos['n2']} ambiguos abiertos"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0023_progreso_practica_comision'),
        ('cursos', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(_backfill_intentos, migrations.RunPython.noop),
        migrations.RunPython(_backfill_progresos, migrations.RunPython.noop),
    ]
