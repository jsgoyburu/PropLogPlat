"""Tests del management command exportar_cohorte."""
import csv
import datetime
import io
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from cursos.models import Cohorte, Comision, Inscripcion, Parcial, NotaParcial

Usuario = get_user_model()


def _u(username, **kwargs):
    user = Usuario.objects.create_user(username=username, password='x', **kwargs)
    Usuario.objects.filter(pk=user.pk).update(
        consentimiento_pedagogico=True,
        consentimiento_investigacion=True,
        encuesta_completada=True,
    )
    user.refresh_from_db()
    return user


class ExportarCohorteTests(TestCase):

    def setUp(self):
        self.docente = _u('exp_doc', es_docente=True)
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC 2026-1')
        self.comision.docentes.add(self.docente)
        self.est1 = _u('exp_est1')
        self.est2 = _u('exp_est2')
        Inscripcion.objects.create(estudiante=self.est1, comision=self.comision, cohorte=self.cohorte)
        Inscripcion.objects.create(estudiante=self.est2, comision=self.comision, cohorte=self.cohorte)
        self.parcial = Parcial.objects.create(
            comision=self.comision,
            cohorte=self.cohorte,
            nombre='1er Parcial',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('10.00'),
        )

    def _call_command(self, comision_id, parcial_id=None):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        args = [str(comision_id)]
        if parcial_id:
            args += ['--parcial-id', str(parcial_id)]
        call_command('exportar_cohorte', *args, stdout=out)
        out.seek(0)
        return list(csv.DictReader(out))

    def test_exporta_una_fila_por_estudiante(self):
        rows = self._call_command(self.comision.id)
        self.assertEqual(len(rows), 2)

    def test_encabezados_presentes(self):
        rows = self._call_command(self.comision.id)
        expected_headers = [
            'id_anon', 'facultad', 'carrera', 'puntaje_logicas', 'categoria_nse',
            'ausente_1p', 'nota_global_1p', 'desenlace_1p',
            'intentos_totales', 'tasa_exito',
            'err_tautologia', 'err_polaridad',
        ]
        for h in expected_headers:
            self.assertIn(h, rows[0], f'Falta columna: {h}')

    def test_sin_parcial_desenlace_vacio(self):
        rows = self._call_command(self.comision.id, self.parcial.id)
        for row in rows:
            self.assertEqual(row['ausente_1p'], '')
            self.assertEqual(row['nota_global_1p'], '')
            self.assertEqual(row['desenlace_1p'], '')

    def test_ausente_aparece_en_csv(self):
        NotaParcial.objects.create(
            parcial=self.parcial, estudiante=self.est1, ausente=True,
        )
        NotaParcial.objects.create(
            parcial=self.parcial, estudiante=self.est2, puntaje=Decimal('8.00'),
        )
        rows = self._call_command(self.comision.id, self.parcial.id)
        ausentes = [r for r in rows if r['ausente_1p'] == 'True']
        self.assertEqual(len(ausentes), 1)
        self.assertEqual(ausentes[0]['desenlace_1p'], 'Ausente')

    def test_desenlace_promocion(self):
        NotaParcial.objects.create(
            parcial=self.parcial, estudiante=self.est1, puntaje=Decimal('8.50'),
        )
        rows = self._call_command(self.comision.id, self.parcial.id)
        promovidos = [r for r in rows if r['desenlace_1p'] == 'Promoción']
        self.assertEqual(len(promovidos), 1)

    def test_id_anon_no_expone_username(self):
        rows = self._call_command(self.comision.id)
        for row in rows:
            self.assertNotIn('exp_est1', row['id_anon'])
            self.assertNotIn('exp_est2', row['id_anon'])


class ExportarCohorteCohorteYParcialInconsistentesTests(TestCase):
    """Code review (PR #189, hallazgo 3): si se pasan ``--cohorte-id`` y
    ``--parcial-id`` de cohortes distintas, la explícita ganaba sin
    verificar consistencia contra la cohorte real del parcial. El CSV
    resultante mezclaba las inscripciones de una camada con las notas del
    parcial de otra (recursantes), etiquetando todo bajo la camada
    explícita."""

    def setUp(self):
        self.docente = _u('exp_inc_doc', es_docente=True)
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Inconsistente')
        self.comision.docentes.add(self.docente)
        self.parcial_c1 = Parcial.objects.create(
            comision=self.comision, cohorte=self.c1, nombre='1P',
            fecha=datetime.date(2026, 6, 15), puntaje_total=Decimal('10.00'),
        )

    def test_rechaza_cohorte_id_que_no_coincide_con_la_del_parcial(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command(
                'exportar_cohorte', str(self.comision.id),
                '--parcial-id', str(self.parcial_c1.id),
                '--cohorte-id', str(self.c2.id),
            )

    def test_acepta_cohorte_id_consistente_con_el_parcial(self):
        from django.core.management import call_command

        out = io.StringIO()
        call_command(
            'exportar_cohorte', str(self.comision.id),
            '--parcial-id', str(self.parcial_c1.id),
            '--cohorte-id', str(self.c1.id),
            stdout=out,
        )
        out.seek(0)
        # No debe levantar: solo se verifica que corre sin error.
        list(csv.DictReader(out))


from django.db import IntegrityError, transaction

from cursos.models import Cohorte


class CohorteModelTests(TestCase):
    """La migración de backfill (0009) ya deja creada 2026-C1 activa en la
    base de tests, así que estos tests usan años que no colisionan con ella.
    """

    def test_str_legible(self):
        c = Cohorte.objects.create(anio=2030, cuatrimestre=1)
        self.assertEqual(str(c), '2030 – C1')

    def test_rechaza_anio_cuatrimestre_duplicado(self):
        Cohorte.objects.create(anio=2030, cuatrimestre=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cohorte.objects.create(anio=2030, cuatrimestre=1)

    def test_permite_dos_cohortes_inactivas(self):
        antes = Cohorte.objects.count()
        Cohorte.objects.create(anio=2030, cuatrimestre=1, activa=False)
        Cohorte.objects.create(anio=2030, cuatrimestre=2, activa=False)
        self.assertEqual(Cohorte.objects.count(), antes + 2)

    def test_rechaza_dos_cohortes_activas(self):
        # 2026-C1 activa=True ya existe por el backfill de la migración 0009.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cohorte.objects.create(anio=2030, cuatrimestre=1, activa=True)

    def test_orden_mas_nuevas_primero(self):
        vieja = Cohorte.objects.create(anio=2025, cuatrimestre=2)
        nueva = Cohorte.objects.create(anio=2030, cuatrimestre=1)
        ambas = Cohorte.objects.filter(pk__in=[vieja.pk, nueva.pk])
        self.assertEqual(list(ambas), [nueva, vieja])


class BackfillCohorteTests(TestCase):
    """Verifica el estado post-migración sobre la base de tests."""

    def test_existe_cohorte_2026_c1_activa(self):
        from cursos.models import Cohorte
        cohorte = Cohorte.objects.filter(anio=2026, cuatrimestre=1).first()
        self.assertIsNotNone(cohorte, 'el backfill debe crear 2026-C1')
        self.assertTrue(cohorte.activa)


class CohortePROTECTTests(TestCase):
    def test_no_se_puede_borrar_cohorte_con_inscripciones(self):
        from django.db.models import ProtectedError
        from cursos.models import Cohorte, Comision, Inscripcion

        cohorte = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        comision = Comision.objects.create(nombre='Prueba')
        est = _u('protegido')
        Inscripcion.objects.create(estudiante=est, comision=comision, cohorte=cohorte)

        with self.assertRaises(ProtectedError):
            cohorte.delete()


class ResolucionCohorteTests(TestCase):
    def setUp(self):
        from cursos.models import Cohorte, Comision
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.comision = Comision.objects.create(nombre='IPC Noche')

    def test_cohorte_activa_devuelve_la_marcada(self):
        from cursos.cohortes import cohorte_activa
        self.assertEqual(cohorte_activa(), self.c1)

    def test_cohorte_de_sin_inscripcion_devuelve_none(self):
        from cursos.cohortes import cohorte_de
        est = _u('sin-inscripcion')
        self.assertIsNone(cohorte_de(est, self.comision))

    def test_cohorte_de_devuelve_la_de_su_inscripcion(self):
        from cursos.cohortes import cohorte_de
        from cursos.models import Inscripcion
        est = _u('camada-vieja')
        Inscripcion.objects.create(estudiante=est, comision=self.comision, cohorte=self.c1)
        self.assertEqual(cohorte_de(est, self.comision), self.c1)

    def test_recursante_resuelve_a_la_inscripcion_mas_reciente(self):
        from cursos.cohortes import cohorte_de
        from cursos.models import Inscripcion
        est = _u('recursa')
        vieja = Inscripcion.objects.create(estudiante=est, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.filter(pk=vieja.pk).update(
            fecha_inscripcion=timezone.now() - timedelta(days=200)
        )
        Inscripcion.objects.create(estudiante=est, comision=self.comision, cohorte=self.c2)
        self.assertEqual(cohorte_de(est, self.comision), self.c2)
