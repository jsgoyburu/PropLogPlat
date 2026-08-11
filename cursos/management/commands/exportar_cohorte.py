"""Management command: exportar_cohorte

Exporta los datos de una comisión en formato CSV compatible con el Excel
histórico de la Memoria Profesional (juntas_con_notas_anon.xlsx), con
columnas adicionales de uso de plataforma para el análisis de impacto.

La cohorte a exportar es explícita (``--cohorte-id``), o se infiere del
parcial indicado, o se usa la cohorte activa. Nunca se deriva de fechas.
Las inscripciones se filtran por esa cohorte: sin este filtro el CSV
mezclaba camadas.

Uso:
    python manage.py exportar_cohorte <comision_id>
    python manage.py exportar_cohorte <comision_id> --parcial-id <id>
    python manage.py exportar_cohorte <comision_id> --cohorte-id <id>
    python manage.py exportar_cohorte <comision_id> --parcial-id <id> --output cohorte.csv
"""
import csv
import datetime

from django.core.management.base import BaseCommand, CommandError

from accounts.models import EncuestaEstudiante
from analiticas.calculos import (
    calcular_desenlace_parcial,
    calcular_nse,
    calcular_puntaje_logicas,
    calcular_uso_plataforma_antes_parcial,
)
from cursos.models import Comision, NotaParcial, Parcial


class Command(BaseCommand):
    help = 'Exporta datos de una comisión como CSV comparable con la serie histórica.'

    def add_arguments(self, parser):
        parser.add_argument('comision_id', type=int)
        parser.add_argument('--parcial-id', type=int, default=None,
                            help='ID del 1er parcial para incluir desenlace y uso.')
        parser.add_argument('--cohorte-id', type=int, default=None,
                            help='Cohorte a exportar. Por defecto: la del parcial, o la activa.')
        parser.add_argument('--output', type=str, default=None,
                            help='Ruta del archivo de salida. Por defecto: stdout.')

    def handle(self, *args, **options):
        comision_id = options['comision_id']
        parcial_id = options['parcial_id']

        try:
            comision = Comision.objects.get(pk=comision_id)
        except Comision.DoesNotExist:
            raise CommandError(f'Comisión {comision_id} no existe.')

        parcial = None
        if parcial_id:
            try:
                parcial = Parcial.objects.get(pk=parcial_id, comision=comision)
            except Parcial.DoesNotExist:
                raise CommandError(
                    f'Parcial {parcial_id} no pertenece a la comisión {comision_id}.'
                )

        # Cohorte: explícita, la del parcial, o la activa. Nunca derivada de fechas.
        from cursos.cohortes import cohorte_activa
        from cursos.models import Cohorte

        if options['cohorte_id']:
            try:
                cohorte = Cohorte.objects.get(pk=options['cohorte_id'])
            except Cohorte.DoesNotExist:
                raise CommandError(f'Cohorte {options["cohorte_id"]} no existe.')
            if parcial and parcial.cohorte_id != cohorte.id:
                raise CommandError(
                    f'--cohorte-id {cohorte.id} no coincide con la cohorte del '
                    f'parcial {parcial_id} (cohorte {parcial.cohorte_id}). '
                    'Pasar --cohorte-id consistente con el parcial, u omitirlo '
                    'para que se infiera de --parcial-id.'
                )
        elif parcial:
            cohorte = parcial.cohorte
        else:
            cohorte = cohorte_activa()

        if cohorte is None:
            raise CommandError(
                'No hay cohorte activa ni parcial indicado. Pasar --cohorte-id.'
            )

        anio = cohorte.anio
        cuatri = cohorte.cuatrimestre

        inscripciones = (
            comision.inscripciones
            .filter(cohorte=cohorte)
            .select_related('estudiante')
            .order_by(
                'estudiante__last_name',
                'estudiante__first_name',
                'estudiante__username',
            )
        )

        # Precargar encuestas y notas
        estudiante_ids = [i.estudiante_id for i in inscripciones]
        encuestas = {
            e.estudiante_id: e
            for e in EncuestaEstudiante.objects.filter(
                estudiante_id__in=estudiante_ids
            )
        }
        notas = {}
        if parcial:
            notas = {
                n.estudiante_id: n
                for n in NotaParcial.objects.filter(parcial=parcial)
            }

        out_file = (
            open(options['output'], 'w', newline='', encoding='utf-8')
            if options['output']
            else self.stdout
        )

        try:
            writer = csv.DictWriter(
                out_file, fieldnames=_COLUMNAS, extrasaction='ignore'
            )
            writer.writeheader()

            for idx, inscripcion in enumerate(inscripciones, start=1):
                est = inscripcion.estudiante
                encuesta = encuestas.get(est.pk)
                nota = notas.get(est.pk)

                row = _fila_base(est, idx, anio, cuatri, encuesta)

                if nota:
                    row['ausente_1p'] = nota.ausente
                    row['nota_global_1p'] = (
                        '' if nota.puntaje is None else nota.puntaje
                    )
                    row['nota_logica_1p'] = (
                        '' if nota.nota_logica_parcial is None else nota.nota_logica_parcial
                    )
                    row['desenlace_1p'] = calcular_desenlace_parcial(nota) or ''

                if parcial and encuesta and est.consentimiento_pedagogico:
                    uso = calcular_uso_plataforma_antes_parcial(est, parcial)
                    row.update(uso)

                writer.writerow(row)
        finally:
            if options['output']:
                out_file.close()

        if options['output']:
            self.stdout.write(self.style.SUCCESS(
                f'Exportado: {options["output"]} ({inscripciones.count()} estudiantes)'
            ))


_ERROR_CATS = [
    'tautologia', 'contradiccion', 'polaridad', 'mas_fuerte', 'mas_debil',
    'equivalente_alt', 'error_parcial_1', 'error_parcial_2', 'error_sistemico',
    'variables_extra', 'variables_menos',
]

_COLUMNAS = [
    # Bloque A — Encuesta (réplica del Excel histórico)
    'id_anon', 'edad', 'facultad', 'carrera',
    'origen_caba_gba', 'vive_en', 'mudado_con_familia', 'mudado_para_trabajar_estudiar',
    'tiempo_mudado', 'desde_donde', 'provincia_origen', 'pais_origen',
    'tiene_cud', 'con_quien_vive', 'tiempo_viaje_puan',
    'situacion_laboral', 'dias_trabaja',
    'acceso_internet', 'celular', 'tablet', 'pc_escritorio', 'computadora_portatil',
    'tiempo_desde_secundaria', 'tipo_escuela',
    'estudios_superiores', 'termino_cbc_anterior', 'se_recibio_uba', 'se_recibio_fuera_uba',
    'hizo_uba_xxi', 'tiempo_en_cbc', 'interrupcion_cbc',
    'ya_curso_ipc', 'motivo_no_termino_ipc', 'materias_aprobadas',
    'acertijo_silogismo', 'acertijo_cirugia_respuesta', 'acertijo_hilera',
    'puntaje_logicas', 'puntaje_nse', 'categoria_nse',
    'anio', 'cuatri',
    # Bloque B — Desenlace 1P
    'ausente_1p', 'nota_global_1p', 'nota_logica_1p', 'desenlace_1p',
    # Bloque C — Uso de plataforma
    'intentos_totales', 'ejercicios_distintos', 'practicas_abiertas',
    'ejercicios_resueltos', 'tasa_exito', 'promedio_intentos_hasta_correcto',
    'dias_activos', 'dias_primer_uso_hasta_1p', 'dias_ultimo_uso_hasta_1p',
] + [f'err_{c}' for c in _ERROR_CATS]


def _fila_base(est, idx, anio, cuatri, encuesta):
    """Construye la fila base con datos de encuesta o vacíos si no hay encuesta."""
    row = {col: '' for col in _COLUMNAS}
    row['id_anon'] = f'{anio}-{cuatri}-{idx}'
    row['anio'] = anio
    row['cuatri'] = cuatri

    if not encuesta:
        return row

    # Edad al inicio del cuatrimestre
    if encuesta.fecha_nacimiento:
        ref = datetime.date(anio, 3 if cuatri == 1 else 8, 1)
        edad = (ref - encuesta.fecha_nacimiento).days // 365
        row['edad'] = edad

    row['facultad'] = encuesta.facultad or ''
    row['carrera'] = encuesta.carrera or ''
    row['origen_caba_gba'] = (
        encuesta.origen_caba_gba if encuesta.origen_caba_gba is not None else ''
    )
    row['vive_en'] = encuesta.vive_en or ''
    row['mudado_con_familia'] = (
        encuesta.mudado_con_familia if encuesta.mudado_con_familia is not None else ''
    )
    row['mudado_para_trabajar_estudiar'] = (
        encuesta.mudado_para_trabajar_estudiar
        if encuesta.mudado_para_trabajar_estudiar is not None
        else ''
    )
    row['tiempo_mudado'] = encuesta.tiempo_mudado or ''
    row['desde_donde'] = encuesta.desde_donde or ''
    row['provincia_origen'] = encuesta.provincia_origen or ''
    row['pais_origen'] = encuesta.pais_origen or ''
    row['tiene_cud'] = (
        encuesta.tiene_cud if encuesta.tiene_cud is not None else ''
    )
    row['con_quien_vive'] = encuesta.con_quien_vive or ''
    row['tiempo_viaje_puan'] = encuesta.tiempo_viaje_puan or ''
    row['situacion_laboral'] = encuesta.situacion_laboral or ''
    row['dias_trabaja'] = encuesta.dias_trabaja or ''

    dispositivos = encuesta.dispositivos or {}
    row['celular'] = dispositivos.get('celular', '')
    row['tablet'] = dispositivos.get('tablet', '')
    row['pc_escritorio'] = dispositivos.get('pc', '')
    row['computadora_portatil'] = dispositivos.get('laptop', '')
    row['acceso_internet'] = ';'.join(encuesta.acceso_internet or [])

    row['tiempo_desde_secundaria'] = encuesta.tiempo_desde_secundaria or ''
    row['tipo_escuela'] = encuesta.tipo_escuela or ''
    row['estudios_superiores'] = encuesta.estudios_superiores or ''
    row['termino_cbc_anterior'] = (
        encuesta.termino_cbc_anterior
        if encuesta.termino_cbc_anterior is not None
        else ''
    )
    row['se_recibio_uba'] = (
        encuesta.se_recibio_uba if encuesta.se_recibio_uba is not None else ''
    )
    row['se_recibio_fuera_uba'] = (
        encuesta.se_recibio_fuera_uba
        if encuesta.se_recibio_fuera_uba is not None
        else ''
    )
    row['hizo_uba_xxi'] = (
        encuesta.hizo_uba_xxi if encuesta.hizo_uba_xxi is not None else ''
    )
    row['tiempo_en_cbc'] = encuesta.tiempo_en_cbc or ''
    row['interrupcion_cbc'] = encuesta.interrupcion_cbc or ''
    row['ya_curso_ipc'] = (
        encuesta.ya_curso_ipc if encuesta.ya_curso_ipc is not None else ''
    )
    row['motivo_no_termino_ipc'] = encuesta.motivo_no_termino_ipc or ''
    row['materias_aprobadas'] = (
        encuesta.materias_aprobadas if encuesta.materias_aprobadas is not None else ''
    )

    row['acertijo_silogismo'] = encuesta.acertijo_silogismo or ''
    # `acertijo_cirugia` is the raw text answer; CSV column is `acertijo_cirugia_respuesta`
    row['acertijo_cirugia_respuesta'] = encuesta.acertijo_cirugia or ''
    row['acertijo_hilera'] = encuesta.acertijo_hilera or ''
    row['puntaje_logicas'] = calcular_puntaje_logicas(encuesta)

    puntaje_nse, cat_nse = calcular_nse(encuesta)
    row['puntaje_nse'] = puntaje_nse
    row['categoria_nse'] = cat_nse

    return row
