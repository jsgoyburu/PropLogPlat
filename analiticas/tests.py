"""Tests para analiticas/research.py y la corrección de _distribucion_intentos.

Cubre:
  - API uniforme: comision_ids=None (global) y comision_ids=[...] (filtrado)
  - desagregar_por_comision: resultado por comisión
  - intentos_hasta_correcto_sin_sesgo: incluye no-resolvieron
  - desacople_docente_maquina: detecta ambos casos de desacople
  - tasa_entrada_efectiva: proporción de quienes llegan
  - tasa_abandono_local: sobre prácticas cerradas y abiertas
  - persistencia_relativa: distingue abandono de persistencia
  - _distribucion_intentos en views.py: campos nuevos presentes
  - Correctitud efectiva: aprobado_docente tiene precedencia sobre es_correcto
"""

import html
import json as _json
import re
import uuid
from datetime import date, datetime
from types import SimpleNamespace

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import EncuestaEstudiante
from cursos.models import Cohorte, Comision, Inscripcion
from ejercicios.models import Ejercicio, EjercicioPractica, Intento, Practica, PracticaComision, Progreso

from analiticas.research import (
    _metricas_desempeno_por_estudiante,
    categorizar_nse,
    clasificacion_pandemia_encuesta,
    desacople_docente_maquina,
    desagregar_por_comision,
    desempeno_por_nse_onboarding,
    desempeno_por_puntaje_logicas,
    distribucion_nse_onboarding,
    intentos_hasta_correcto_sin_sesgo,
    perfiles_encuesta_onboarding,
    persistencia_relativa,
    puntaje_logicas_encuesta,
    puntaje_nse_encuesta,
    tasa_abandono_local,
    tasa_entrada_efectiva,
)
from analiticas.views import (
    _concentracion_practica,
    _distribucion_intentos,
    _ejercicios_mas_dificiles,
    _errores_sistematicos,
    _estudiantes_en_riesgo,
    _evolucion_temporal,
    _silencio_temprano,
    _velocidad_arranque,
)

User = get_user_model()


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _u(username, **kwargs):
    """Crea un usuario de prueba que, por defecto, es sujeto de investigación.

    research.py filtra dos veces sobre los datos de investigación:
      - ``solo_consentimiento=True`` (default desde 3be6c7f) exige
        ``consentimiento_investigacion=True``;
      - el pipeline pseudonimizado (130f7bb) exige además ``research_id``
        no nulo, porque agrupa por ``research_id.hex`` en vez de por PK.

    El flujo real (``accounts/views.py::_guardar_consentimientos``) genera el
    ``research_id`` en el mismo momento en que registra el consentimiento, así
    que ambos campos van juntos. Las fixtures replican ese invariante; los
    tests que necesitan un usuario sin consentimiento lo piden explícitamente
    pasando ``consentimiento_investigacion=False``.
    """
    kwargs.setdefault('consentimiento_investigacion', True)
    if kwargs.get('consentimiento_investigacion'):
        kwargs.setdefault('research_id', uuid.uuid4())
    return User.objects.create_user(username=username, password='clave123', **kwargs)


def _cohorte():
    """La cohorte 2026-C1 que deja creada la migración de backfill (0009)."""
    return Cohorte.objects.get(anio=2026, cuatrimestre=1)


def _crear_encuesta(estudiante, **kwargs):
    """Crea una EncuestaEstudiante mínima para el estudiante dado.

    ``_registros_encuesta`` exige ``estudiante__encuesta__isnull=False``:
    sin esta fixture el estudiante no aparece en ninguna función de la
    familia encuesta, aunque tenga consentimiento_investigacion=True.
    """
    return EncuestaEstudiante.objects.create(estudiante=estudiante, **kwargs)


def _intento(estudiante, ep, es_correcto, aprobado_docente=None, *, pc):
    return Intento.objects.create(
        estudiante=estudiante,
        ejercicio_practica=ep,
        respuesta_raw='p',
        es_correcto=es_correcto,
        aprobado_docente=aprobado_docente,
        practica_comision=pc,
        cohorte=_cohorte(),
    )


def _setup_comision(nombre, n_estudiantes=0, with_practica=True):
    """Crea una comisión con docente, opcionalmente con práctica y EP."""
    docente = _u(f'doc-{nombre}', es_docente=True)
    comision = Comision.objects.create(nombre=nombre)
    comision.docentes.add(docente)
    estudiantes = [_u(f'est-{nombre}-{i}') for i in range(n_estudiantes)]
    for est in estudiantes:
        Inscripcion.objects.create(estudiante=est, comision=comision, cohorte=_cohorte())
    ep = None
    practica = None
    pc = None
    if with_practica:
        practica = Practica.objects.create(titulo=f'P-{nombre}')
        pc = PracticaComision.objects.create(practica=practica, comision=comision, orden=1)
        ejercicio = Ejercicio.objects.create(
            enunciado=f'Ej {nombre}', formula_solucion='p',
            tipo='formalizacion', creado_por=docente,
        )
        ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
    return comision, practica, pc, ep, estudiantes


# ─── Tests: _distribucion_intentos (views.py) ────────────────────────────────

class DistribucionIntentosSinSesgoTests(TestCase):

    def setUp(self):
        self.comision, self.practica, self.pc, self.ep, self.estudiantes = _setup_comision(
            'dis', n_estudiantes=2,
        )
        # est0 resuelve en 2 intentos
        _intento(self.estudiantes[0], self.ep, False, pc=self.pc)
        _intento(self.estudiantes[0], self.ep, True, pc=self.pc)
        # est1 nunca resuelve (3 intentos)
        _intento(self.estudiantes[1], self.ep, False, pc=self.pc)
        _intento(self.estudiantes[1], self.ep, False, pc=self.pc)
        _intento(self.estudiantes[1], self.ep, False, pc=self.pc)

    def test_no_resolvieron_presente(self):
        ids = [e.id for e in self.estudiantes]
        resultado = _distribucion_intentos([self.comision.id], ids)
        fila = resultado[0]
        self.assertEqual(fila['no_resolvieron'], 1)
        self.assertEqual(fila['resolvieron'], 1)

    def test_pct_no_resolvio(self):
        ids = [e.id for e in self.estudiantes]
        fila = _distribucion_intentos([self.comision.id], ids)[0]
        self.assertAlmostEqual(fila['pct_no_resolvio'], 50.0)

    def test_mediana_presente(self):
        ids = [e.id for e in self.estudiantes]
        fila = _distribucion_intentos([self.comision.id], ids)[0]
        self.assertIsNotNone(fila['mediana'])

    def test_todos_resuelven_no_resolvieron_es_cero(self):
        c2, _p, pc2, ep2, ests = _setup_comision('dis2', n_estudiantes=1)
        _intento(ests[0], ep2, True, pc=pc2)
        fila = _distribucion_intentos([c2.id], [e.id for e in ests])[0]
        self.assertEqual(fila['no_resolvieron'], 0)
        self.assertEqual(fila['pct_no_resolvio'], 0.0)


# ─── Tests: research.py — API uniforme ───────────────────────────────────────

class IntentosSinSesgoTests(TestCase):

    def setUp(self):
        self.c1, _p, self.pc, self.ep, _ests = _setup_comision('res1', n_estudiantes=0)
        # est1 resuelve en 3 intentos
        est1 = _u('res1-e1')
        _intento(est1, self.ep, False, pc=self.pc)
        _intento(est1, self.ep, False, pc=self.pc)
        _intento(est1, self.ep, True, pc=self.pc)
        # est2 nunca resuelve (2 intentos)
        est2 = _u('res1-e2')
        _intento(est2, self.ep, False, pc=self.pc)
        _intento(est2, self.ep, False, pc=self.pc)
        # est3 resuelve en 1 intento
        est3 = _u('res1-e3')
        _intento(est3, self.ep, True, pc=self.pc)

    def test_resolvieron_y_no_resolvieron(self):
        resultado = intentos_hasta_correcto_sin_sesgo(ep_ids=[self.ep.id])
        fila = resultado[0]
        self.assertEqual(fila['resolvieron'], 2)
        self.assertEqual(fila['no_resolvieron'], 1)

    def test_pct_no_resolvio(self):
        fila = intentos_hasta_correcto_sin_sesgo(ep_ids=[self.ep.id])[0]
        self.assertAlmostEqual(fila['pct_no_resolvio'], 33.3)

    def test_mediana(self):
        # resolvieron en 3 y 1 intentos → mediana = 2.0
        fila = intentos_hasta_correcto_sin_sesgo(ep_ids=[self.ep.id])[0]
        self.assertEqual(fila['mediana_hasta_correcto'], 2.0)

    def test_comision_id_en_resultado(self):
        fila = intentos_hasta_correcto_sin_sesgo(ep_ids=[self.ep.id])[0]
        self.assertEqual(fila['comision_id'], self.c1.id)

    def test_via_comision_ids(self):
        """Llamada sin ep_ids explícitos: deriva de comision_ids."""
        resultado = intentos_hasta_correcto_sin_sesgo(comision_ids=[self.c1.id])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['ep_id'], self.ep.id)

    def test_global_sin_argumentos(self):
        """comision_ids=None → incluye todos los EPs del sistema."""
        resultado = intentos_hasta_correcto_sin_sesgo()
        ep_ids_resultado = [r['ep_id'] for r in resultado]
        self.assertIn(self.ep.id, ep_ids_resultado)

    def test_ep_sin_intentos(self):
        _c, _p, _pc, ep_vacio, _ests = _setup_comision('res-vacio', n_estudiantes=0)
        fila = intentos_hasta_correcto_sin_sesgo(ep_ids=[ep_vacio.id])[0]
        self.assertEqual(fila['resolvieron'], 0)
        self.assertIsNone(fila['mediana_hasta_correcto'])


class DesacopleDocenteMaquinaTests(TestCase):

    def setUp(self):
        self.c1, _p, self.pc1, self.ep, self.ests = _setup_comision('desa', n_estudiantes=1)
        self.c2, _p2, self.pc2, self.ep2, self.ests2 = _setup_comision('desa2', n_estudiantes=1)

    def test_maquina_ok_docente_no(self):
        _intento(self.ests[0], self.ep, es_correcto=True, aprobado_docente=False, pc=self.pc1)
        r = desacople_docente_maquina(comision_ids=[self.c1.id])
        self.assertEqual(r['maquina_ok_docente_no'], 1)
        self.assertAlmostEqual(r['tasa_desacople'], 1.0)

    def test_maquina_no_docente_ok(self):
        _intento(self.ests[0], self.ep, es_correcto=False, aprobado_docente=True, pc=self.pc1)
        r = desacople_docente_maquina(comision_ids=[self.c1.id])
        self.assertEqual(r['maquina_no_docente_ok'], 1)
        self.assertAlmostEqual(r['tasa_desacople'], 1.0)

    def test_acuerdo_no_es_desacople(self):
        _intento(self.ests[0], self.ep, es_correcto=True, aprobado_docente=True, pc=self.pc1)
        r = desacople_docente_maquina(comision_ids=[self.c1.id])
        self.assertEqual(r['acuerdo'], 1)
        self.assertAlmostEqual(r['tasa_desacople'], 0.0)

    def test_sin_revision_no_cuenta(self):
        _intento(self.ests[0], self.ep, es_correcto=False, aprobado_docente=None, pc=self.pc1)
        r = desacople_docente_maquina(comision_ids=[self.c1.id])
        self.assertEqual(r['total_revisados'], 0)
        self.assertIsNone(r['tasa_desacople'])

    def test_global_agrega_ambas_comisiones(self):
        _intento(self.ests[0], self.ep, es_correcto=True, aprobado_docente=False, pc=self.pc1)
        _intento(self.ests2[0], self.ep2, es_correcto=True, aprobado_docente=False, pc=self.pc2)
        r = desacople_docente_maquina(comision_ids=[self.c1.id, self.c2.id])
        self.assertEqual(r['total_revisados'], 2)


class TasaEntradaEfectivaTests(TestCase):

    def setUp(self):
        self.c1, self.practica, self.pc, self.ep, self.ests = _setup_comision('ent', n_estudiantes=3)
        # 2 de 3 intentan
        _intento(self.ests[0], self.ep, False, pc=self.pc)
        _intento(self.ests[1], self.ep, True, pc=self.pc)

    def test_tasa_correcta(self):
        resultado = tasa_entrada_efectiva(comision_ids=[self.c1.id])
        fila = next(r for r in resultado if r['practica_id'] == self.practica.id)
        self.assertEqual(fila['con_intento'], 2)
        self.assertEqual(fila['sin_intento'], 1)
        self.assertAlmostEqual(fila['tasa_entrada'], 2 / 3, places=3)

    def test_comision_id_en_resultado(self):
        resultado = tasa_entrada_efectiva(comision_ids=[self.c1.id])
        self.assertTrue(all(r['comision_id'] == self.c1.id for r in resultado))

    def test_dos_comisiones_en_resultado(self):
        c2, p2, pc2, ep2, ests2 = _setup_comision('ent2', n_estudiantes=2)
        _intento(ests2[0], ep2, True, pc=pc2)
        resultado = tasa_entrada_efectiva(comision_ids=[self.c1.id, c2.id])
        comisiones_en_resultado = {r['comision_id'] for r in resultado}
        self.assertIn(self.c1.id, comisiones_en_resultado)
        self.assertIn(c2.id, comisiones_en_resultado)

    def test_nadie_intento(self):
        c2, p2, _pc, _ep, _ests = _setup_comision('ent-vacia', n_estudiantes=2)
        resultado = tasa_entrada_efectiva(comision_ids=[c2.id])
        fila = next(r for r in resultado if r['practica_id'] == p2.id)
        self.assertEqual(fila['con_intento'], 0)
        self.assertAlmostEqual(fila['tasa_entrada'], 0.0)


class PersistenciaRelativaTests(TestCase):

    def setUp(self):
        self.c1, _p, self.pc, self.ep, _ests = _setup_comision('pers', n_estudiantes=0)
        est1 = _u('pers-e1')
        _intento(est1, self.ep, False, pc=self.pc)
        _intento(est1, self.ep, True, pc=self.pc)  # persistió
        est2 = _u('pers-e2')
        _intento(est2, self.ep, False, pc=self.pc)  # abandonó

    def test_persistio_vs_abandono(self):
        resultado = persistencia_relativa(ep_ids=[self.ep.id])
        fila = resultado[0]
        self.assertEqual(fila['persistieron'], 1)
        self.assertEqual(fila['abandonaron'], 1)
        self.assertAlmostEqual(fila['tasa_persistencia'], 0.5)

    def test_comision_id_en_resultado(self):
        fila = persistencia_relativa(ep_ids=[self.ep.id])[0]
        self.assertEqual(fila['comision_id'], self.c1.id)

    def test_via_comision_ids(self):
        resultado = persistencia_relativa(comision_ids=[self.c1.id])
        self.assertTrue(any(r['ep_id'] == self.ep.id for r in resultado))

    def test_sin_fallos(self):
        _c, _p, pc2, ep2, _ests = _setup_comision('pers2', n_estudiantes=0)
        est = _u('pers2-e1')
        _intento(est, ep2, True, pc=pc2)
        fila = persistencia_relativa(ep_ids=[ep2.id])[0]
        self.assertEqual(fila['intentaron_con_fallo'], 0)
        self.assertIsNone(fila['tasa_persistencia'])


class DesagregarPorComisionTests(TestCase):
    """Verifica que desagregar_por_comision devuelve un dict por comisión."""

    def setUp(self):
        self.c1, _p, self.pc1, self.ep1, self.ests1 = _setup_comision('dag1', n_estudiantes=1)
        self.c2, _p2, self.pc2, self.ep2, self.ests2 = _setup_comision('dag2', n_estudiantes=1)
        _intento(self.ests1[0], self.ep1, True, aprobado_docente=False, pc=self.pc1)
        _intento(self.ests2[0], self.ep2, False, aprobado_docente=True, pc=self.pc2)

    def test_claves_son_comision_ids(self):
        resultado = desagregar_por_comision(
            desacople_docente_maquina,
            comision_ids=[self.c1.id, self.c2.id],
        )
        self.assertIn(self.c1.id, resultado)
        self.assertIn(self.c2.id, resultado)

    def test_valores_son_independientes(self):
        resultado = desagregar_por_comision(
            desacople_docente_maquina,
            comision_ids=[self.c1.id, self.c2.id],
        )
        # c1 tiene maquina_ok_docente_no=1, c2 tiene maquina_no_docente_ok=1
        self.assertEqual(resultado[self.c1.id]['maquina_ok_docente_no'], 1)
        self.assertEqual(resultado[self.c2.id]['maquina_no_docente_ok'], 1)
        self.assertEqual(resultado[self.c1.id]['maquina_no_docente_ok'], 0)
        self.assertEqual(resultado[self.c2.id]['maquina_ok_docente_no'], 0)


class DefaultSoloConsentimientoTests(TestCase):
    """El default ``solo_consentimiento=True`` excluye a quienes no consintieron.

    Guarda el cambio de 3be6c7f (invertir el default False→True). El resto de
    las fixtures crea estudiantes que sí consintieron, así que sin este test un
    retroceso del default pasaría inadvertido.
    """

    def setUp(self):
        self.comision, self.practica, self.pc, self.ep, self.ests = _setup_comision(
            'consent', n_estudiantes=1,
        )
        self.sin_consent = _u('consent-no', consentimiento_investigacion=False)
        Inscripcion.objects.create(estudiante=self.sin_consent, comision=self.comision, cohorte=_cohorte())
        _intento(self.ests[0], self.ep, True, aprobado_docente=False, pc=self.pc)
        _intento(self.sin_consent, self.ep, True, aprobado_docente=False, pc=self.pc)

    def test_desacople_excluye_sin_consentimiento_por_default(self):
        por_default = desacople_docente_maquina(comision_ids=[self.comision.id])
        self.assertEqual(por_default['total_revisados'], 1)

        explicito = desacople_docente_maquina(
            comision_ids=[self.comision.id], solo_consentimiento=False,
        )
        self.assertEqual(explicito['total_revisados'], 2)

    def test_tasa_entrada_excluye_sin_consentimiento_por_default(self):
        def _fila(**kwargs):
            resultado = tasa_entrada_efectiva(comision_ids=[self.comision.id], **kwargs)
            return next(r for r in resultado if r['practica_id'] == self.practica.id)

        # Numerador y denominador se restringen juntos: poblaciones comparables.
        por_default = _fila()
        self.assertEqual(por_default['total_estudiantes'], 1)
        self.assertEqual(por_default['con_intento'], 1)

        explicito = _fila(solo_consentimiento=False)
        self.assertEqual(explicito['total_estudiantes'], 2)
        self.assertEqual(explicito['con_intento'], 2)


class EncuestaOnboardingResearchTests(TestCase):

    def setUp(self):
        self.docente = _u('doc-encuesta', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC 2025 C1')
        self.comision.docentes.add(self.docente)

        self.practica = Practica.objects.create(titulo='Práctica encuesta')
        self.pc = PracticaComision.objects.create(
            practica=self.practica,
            comision=self.comision,
            orden=1,
        )
        self.ejercicio = Ejercicio.objects.create(
            enunciado='Formalizá p',
            formula_solucion='p',
            tipo='formalizacion',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(practica=self.practica, ejercicio=self.ejercicio, orden=1)

        self.est_alto = _u('est-alto', consentimiento_investigacion=True)
        self.est_bajo = _u('est-bajo', consentimiento_investigacion=True)
        self.est_sin_consent = _u('est-sin-consent', consentimiento_investigacion=False)
        # Fila deliberadamente inconsistente: consentimiento=False pero CON
        # research_id. El flujo real no la produce (accounts/views.py anula el
        # research_id al revocar y poblar_research_id repara las que queden),
        # pero es justo el caso que _filtrar_por_consentimiento existe para
        # cubrir: research.py aplica dos filtros independientes y, con
        # research_id=None, el gate research_id__isnull=False excluiría al
        # estudiante por su cuenta y estos tests seguirían en verde aunque el
        # filtro de consentimiento desapareciera. Con pseudónimo no nulo, el
        # consentimiento es lo único que puede dejarla afuera.
        User.objects.filter(pk=self.est_sin_consent.pk).update(research_id=uuid.uuid4())
        self.est_sin_consent.refresh_from_db()

        self.ins_alto = Inscripcion.objects.create(estudiante=self.est_alto, comision=self.comision, cohorte=_cohorte())
        self.ins_bajo = Inscripcion.objects.create(estudiante=self.est_bajo, comision=self.comision, cohorte=_cohorte())
        self.ins_sin = Inscripcion.objects.create(estudiante=self.est_sin_consent, comision=self.comision, cohorte=_cohorte())
        Inscripcion.objects.filter(pk=self.ins_alto.pk).update(fecha_inscripcion=timezone.make_aware(datetime(2025, 3, 10, 10, 0, 0)))
        Inscripcion.objects.filter(pk=self.ins_bajo.pk).update(fecha_inscripcion=timezone.make_aware(datetime(2025, 8, 12, 10, 0, 0)))
        Inscripcion.objects.filter(pk=self.ins_sin.pk).update(fecha_inscripcion=timezone.make_aware(datetime(2025, 8, 12, 10, 0, 0)))

        self.enc_alto = EncuestaEstudiante.objects.create(
            estudiante=self.est_alto,
            fecha_nacimiento=date(2004, 1, 1),
            facultad='filosofia',
            carrera='filosofia',
            con_quien_vive='solo',
            tiempo_viaje_puan='menos_30',
            situacion_laboral='no_trabajo',
            dias_trabaja='no',
            dispositivos={'celular': 'individual', 'tablet': 'individual', 'pc': 'individual', 'laptop': 'individual'},
            estudios_superiores='si_uba',
            se_recibio_uba=True,
            hizo_uba_xxi=True,
            tiempo_en_cbc='segundo',
            materias_aprobadas=3,
            mudado_para_trabajar_estudiar=False,
            tiene_cud=False,
            acertijo_silogismo='mas_bajo',
            acertijo_cirugia='La madre del niño',
            acertijo_hilera='rodriguez',
        )
        self.enc_bajo = EncuestaEstudiante.objects.create(
            estudiante=self.est_bajo,
            fecha_nacimiento=date(1999, 1, 1),
            facultad='sociales',
            carrera='sociologia',
            con_quien_vive='residencia',
            tiempo_viaje_puan='mas_90',
            situacion_laboral='busco',
            dias_trabaja='no',
            dispositivos={'celular': 'compartido'},
            estudios_superiores='no',
            hizo_uba_xxi=False,
            tiempo_en_cbc='primero',
            materias_aprobadas=0,
            mudado_para_trabajar_estudiar=True,
            tiene_cud=True,
            acertijo_silogismo='mas_alto',
            acertijo_cirugia='No sé',
            acertijo_hilera='rivera',
        )
        self.enc_sin = EncuestaEstudiante.objects.create(
            estudiante=self.est_sin_consent,
            fecha_nacimiento=date(2007, 1, 1),
            facultad='psicologia',
            carrera='psicologia',
            acertijo_silogismo='mas_alto',
            acertijo_hilera='rivera',
        )

        Intento.objects.create(
            estudiante=self.est_alto,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=_cohorte(),
            respuesta_raw='q',
            es_correcto=False,
        )
        Intento.objects.create(
            estudiante=self.est_alto,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=_cohorte(),
            respuesta_raw='p',
            es_correcto=True,
        )
        Intento.objects.create(
            estudiante=self.est_bajo,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=_cohorte(),
            respuesta_raw='q',
            es_correcto=False,
        )
        Progreso.objects.create(estudiante=self.est_alto, practica_comision=self.pc, cohorte=_cohorte(), ejercicio_practica_actual=None)
        Progreso.objects.create(estudiante=self.est_bajo, practica_comision=self.pc, cohorte=_cohorte(), ejercicio_practica_actual=self.ep)

    def test_indices_replican_heuristicas_del_notebook(self):
        self.assertGreaterEqual(puntaje_nse_encuesta(self.enc_alto), 2.5)
        self.assertEqual(categorizar_nse(puntaje_nse_encuesta(self.enc_alto)), 'Alto')
        self.assertLess(puntaje_nse_encuesta(self.enc_bajo), -2.5)
        self.assertEqual(categorizar_nse(puntaje_nse_encuesta(self.enc_bajo)), 'Muy bajo')
        self.assertEqual(puntaje_logicas_encuesta(self.enc_alto), 3)
        self.assertEqual(puntaje_logicas_encuesta(self.enc_bajo), 0)
        self.assertEqual(clasificacion_pandemia_encuesta(self.enc_alto), 'SÍ')
        self.assertEqual(clasificacion_pandemia_encuesta(self.enc_bajo), 'PREVIO')
        self.assertEqual(clasificacion_pandemia_encuesta(self.enc_sin), 'NO')

    def test_perfiles_y_distribucion_filtran_por_consentimiento(self):
        perfiles = perfiles_encuesta_onboarding(comision_ids=[self.comision.id], solo_consentimiento=True)
        self.assertEqual(len(perfiles), 2)
        categorias = {fila['categoria_nse'] for fila in perfiles}
        self.assertEqual(categorias, {'Alto', 'Muy bajo'})

        distribucion = distribucion_nse_onboarding(comision_ids=[self.comision.id], solo_consentimiento=True)
        self.assertEqual(sum(fila['count'] for fila in distribucion), 2)

    def test_desempeno_por_nse_cruza_encuesta_con_ejercicios(self):
        filas = desempeno_por_nse_onboarding(comision_ids=[self.comision.id], solo_consentimiento=True)
        por_categoria = {fila['categoria_nse']: fila for fila in filas}

        self.assertEqual(por_categoria['Alto']['resolvio_alguno'], 1)
        self.assertEqual(por_categoria['Alto']['con_intento'], 1)
        self.assertAlmostEqual(por_categoria['Alto']['promedio_practicas_completadas'], 1.0)
        self.assertEqual(por_categoria['Muy bajo']['resolvio_alguno'], 0)
        self.assertAlmostEqual(por_categoria['Muy bajo']['promedio_resueltos'], 0.0)

    def test_desempeno_por_puntaje_logicas(self):
        filas = desempeno_por_puntaje_logicas(comision_ids=[self.comision.id], solo_consentimiento=True)
        por_puntaje = {fila['puntaje_logicas']: fila for fila in filas}

        self.assertIn(3, por_puntaje)
        self.assertIn(0, por_puntaje)
        self.assertEqual(por_puntaje[3]['resolvio_alguno'], 1)
        self.assertEqual(por_puntaje[0]['resolvio_alguno'], 0)

    def test_metricas_toleran_encuestas_legacy_con_campos_faltantes(self):
        encuesta_legacy = SimpleNamespace(
            con_quien_vive='solo',
            dispositivos={'pc': 'individual'},
            acertijo_silogismo='mas_bajo',
            acertijo_cirugia='La madre',
            acertijo_hilera='rodriguez',
        )

        self.assertEqual(puntaje_nse_encuesta(encuesta_legacy), 2.0)
        self.assertEqual(puntaje_logicas_encuesta(encuesta_legacy), 3)
        self.assertEqual(clasificacion_pandemia_encuesta(encuesta_legacy), 'Sin datos')

    def test_metricas_desempeno_filtran_consentimiento_en_intentos_y_progreso(self):
        Intento.objects.create(
            estudiante=self.est_sin_consent,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=_cohorte(),
            respuesta_raw='p',
            es_correcto=True,
        )
        Progreso.objects.create(estudiante=self.est_sin_consent, practica_comision=self.pc, cohorte=_cohorte(), ejercicio_practica_actual=None)

        metricas = _metricas_desempeno_por_estudiante(
            comision_ids=[self.comision.id],
            solo_consentimiento=True,
        )

        # El resultado se keyea por research_id.hex (pseudónimo), no por PK:
        # ningún identificador real circula por el pipeline de métricas (130f7bb).
        # est_sin_consent tiene pseudónimo (ver setUp), así que solo el filtro
        # de consentimiento puede excluirlo, tanto en intentos como en progreso.
        self.assertIsNotNone(self.est_sin_consent.research_id)
        self.assertNotIn(self.est_sin_consent.research_id.hex, metricas)
        self.assertEqual(metricas[self.est_alto.research_id.hex]['practicas_completadas'], 1)


# ─── Tests: correctitud efectiva (aprobado_docente) ──────────────────────────

class CorrectitudEfectivaTests(TestCase):
    """Verifica que las métricas usen aprobado_docente como árbitro final."""

    def setUp(self):
        self.comision, self.practica, self.pc, self.ep, self.ests = _setup_comision(
            'efect', n_estudiantes=3,
        )
        self.ests_ids = [e.id for e in self.ests]

    # _ejercicios_mas_dificiles ------------------------------------------------

    def test_maquina_ok_rechazado_cuenta_como_error(self):
        # Tres intentos todos correctos según la máquina, pero el docente rechaza uno.
        # Esperamos 1 error (tasa = 1/3 ≈ 33.3 %).
        for est in self.ests:
            _intento(est, self.ep, es_correcto=True, pc=self.pc)
        # Rechazar el intento del primer estudiante
        Intento.objects.filter(estudiante=self.ests[0]).update(aprobado_docente=False)

        resultado = _ejercicios_mas_dificiles([self.comision.id], self.ests_ids, min_intentos=1)
        self.assertEqual(len(resultado), 1)
        fila = resultado[0]
        self.assertEqual(fila['errores'], 1)
        self.assertEqual(fila['total'], 3)

    def test_maquina_no_aprobado_no_cuenta_como_error(self):
        # Tres intentos incorrectos según la máquina; el docente aprueba uno.
        # Esperamos 2 errores.
        for est in self.ests:
            _intento(est, self.ep, es_correcto=False, pc=self.pc)
        Intento.objects.filter(estudiante=self.ests[0]).update(aprobado_docente=True)

        resultado = _ejercicios_mas_dificiles([self.comision.id], self.ests_ids, min_intentos=1)
        fila = resultado[0]
        self.assertEqual(fila['errores'], 2)

    # _estudiantes_en_riesgo ---------------------------------------------------

    def test_aprobacion_docente_interrumpe_racha(self):
        # 5 intentos incorrectos → el docente aprueba el último.
        # La racha efectiva debe ser 0 (no hay fallos consecutivos al final).
        est = self.ests[0]
        for _ in range(5):
            _intento(est, self.ep, es_correcto=False, pc=self.pc)
        Intento.objects.filter(estudiante=est).order_by('-id').first()
        ultimo = Intento.objects.filter(estudiante=est).order_by('-id').first()
        ultimo.aprobado_docente = True
        ultimo.save(update_fields=['aprobado_docente'])

        en_riesgo = _estudiantes_en_riesgo([self.comision.id], self.ests_ids, umbral_riesgo=5)
        usernames = [e['username'] for e in en_riesgo]
        self.assertNotIn(est.username, usernames)

    def test_rechazo_docente_extiende_racha(self):
        # 4 fallos consecutivos + 1 correcto rechazado por docente = 5 fallos efectivos.
        est = self.ests[0]
        for _ in range(4):
            _intento(est, self.ep, es_correcto=False, pc=self.pc)
        ultimo = _intento(est, self.ep, es_correcto=True, pc=self.pc)
        ultimo.aprobado_docente = False
        ultimo.save(update_fields=['aprobado_docente'])

        en_riesgo = _estudiantes_en_riesgo([self.comision.id], self.ests_ids, umbral_riesgo=5)
        usernames = [e['username'] for e in en_riesgo]
        self.assertIn(est.username, usernames)

    # _distribucion_intentos ---------------------------------------------------

    def test_aprobacion_docente_cuenta_como_resolucion(self):
        # Estudiante con 2 fallos + 1 incorrecto aprobado por docente → resuelto en 3.
        est = self.ests[0]
        _intento(est, self.ep, es_correcto=False, pc=self.pc)
        _intento(est, self.ep, es_correcto=False, pc=self.pc)
        aprobado = _intento(est, self.ep, es_correcto=False, pc=self.pc)
        aprobado.aprobado_docente = True
        aprobado.save(update_fields=['aprobado_docente'])

        resultado = _distribucion_intentos([self.comision.id], self.ests_ids)
        fila = resultado[0]
        self.assertEqual(fila['resolvieron'], 1)
        self.assertEqual(fila['no_resolvieron'], 0)

    def test_rechazo_docente_no_cuenta_como_resolucion(self):
        # Intento correcto según máquina pero rechazado por docente → no resuelto.
        est = self.ests[0]
        rechazado = _intento(est, self.ep, es_correcto=True, pc=self.pc)
        rechazado.aprobado_docente = False
        rechazado.save(update_fields=['aprobado_docente'])

        resultado = _distribucion_intentos([self.comision.id], self.ests_ids)
        fila = resultado[0]
        self.assertEqual(fila['resolvieron'], 0)
        self.assertEqual(fila['no_resolvieron'], 1)

    # _errores_sistematicos ----------------------------------------------------

    def test_aprobado_docente_excluido_de_errores_sistematicos(self):
        # Dos estudiantes con misma respuesta incorrecta, pero el docente aprueba uno.
        # No debe aparecer como error sistemático (solo 1 estudiante con error real).
        for est in self.ests[:2]:
            i = _intento(est, self.ep, es_correcto=False, pc=self.pc)
        Intento.objects.filter(estudiante=self.ests[0]).update(aprobado_docente=True)

        resultado = _errores_sistematicos([self.comision.id], self.ests_ids, min_estudiantes=2)
        self.assertEqual(len(resultado), 0)

    def test_rechazado_docente_incluido_en_errores_sistematicos(self):
        # Dos intentos correctos según máquina, ambos rechazados por el docente.
        # Misma respuesta → debe aparecer como error sistemático.
        for est in self.ests[:2]:
            i = _intento(est, self.ep, es_correcto=True, pc=self.pc)
        Intento.objects.filter(
            estudiante__in=self.ests[:2], ejercicio_practica=self.ep
        ).update(aprobado_docente=False)

        resultado = _errores_sistematicos([self.comision.id], self.ests_ids, min_estudiantes=2)
        self.assertEqual(len(resultado), 1)

    # _evolucion_temporal ------------------------------------------------------

    def test_rechazo_no_suma_a_correctos_en_evolucion(self):
        est = self.ests[0]
        i = _intento(est, self.ep, es_correcto=True, pc=self.pc)
        i.aprobado_docente = False
        i.save(update_fields=['aprobado_docente'])

        resultado = _evolucion_temporal([self.comision.id], self.ests_ids)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['correctos'], 0)

    def test_aprobacion_suma_a_correctos_en_evolucion(self):
        est = self.ests[0]
        i = _intento(est, self.ep, es_correcto=False, pc=self.pc)
        i.aprobado_docente = True
        i.save(update_fields=['aprobado_docente'])

        resultado = _evolucion_temporal([self.comision.id], self.ests_ids)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['correctos'], 1)


class CalcularNseTests(TestCase):
    """Tests para calcular_nse(), réplica de puntaje_nse() de la Memoria."""

    def _encuesta(self, **kwargs):
        """Crea EncuestaEstudiante con campos por defecto neutros (puntaje=0)."""
        from accounts.models import EncuestaEstudiante
        from django.contrib.auth import get_user_model
        Usuario = get_user_model()
        u = Usuario.objects.create_user(username=f'nse_{id(kwargs)}', password='x')
        defaults = dict(
            con_quien_vive='familia_nuclear',  # 0
            dispositivos={'celular': 'individual', 'tablet': 'no_tengo',
                          'pc': 'no_tengo', 'laptop': 'no_tengo'},  # 0
            estudios_superiores='no',          # 0
            hizo_uba_xxi=False,                # 0
            tiempo_en_cbc='primero',           # 0
            materias_aprobadas=None,           # 0
            tiempo_viaje_puan='30_60',         # 0
            situacion_laboral='no_trabajo',
            dias_trabaja='no',                 # +1 (no trabaja + no busca)
            mudado_para_trabajar_estudiar=False,  # 0
            tiene_cud=False,                   # 0
        )
        defaults.update(kwargs)
        enc = EncuestaEstudiante.objects.create(estudiante=u, **defaults)
        return enc

    def test_puntaje_base_no_trabaja_no_busca(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta()
        puntaje, cat = calcular_nse(enc)
        self.assertEqual(puntaje, 1.0)    # solo item 7: no trabaja + no busca
        self.assertEqual(cat, 'Medio alto')

    def test_vivienda_solo_suma(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(con_quien_vive='solo')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 2.0)    # +1 vivienda + 1 laboral

    def test_vivienda_comparte_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(con_quien_vive='amigos')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 vivienda + 1 laboral

    def test_laptop_individual_suma(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(dispositivos={
            'celular': 'individual', 'laptop': 'individual',
            'tablet': 'no_tengo', 'pc': 'no_tengo',
        })
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 2.0)    # +1 laptop + 1 laboral

    def test_celular_compartido_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(dispositivos={
            'celular': 'compartido', 'laptop': 'no_tengo',
            'tablet': 'no_tengo', 'pc': 'no_tengo',
        })
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 celular + 1 laboral

    def test_viaje_menos_30_suma(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(tiempo_viaje_puan='menos_30')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 2.0)    # +1 viaje + 1 laboral

    def test_viaje_largo_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(tiempo_viaje_puan='mas_90')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 viaje + 1 laboral

    def test_cud_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(tiene_cud=True)
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 CUD + 1 laboral

    def test_migracion_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(mudado_para_trabajar_estudiar=True)
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, 0.0)    # -1 migración + 1 laboral

    def test_busca_trabajo_resta(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(situacion_laboral='busco', dias_trabaja='no')
        puntaje, _ = calcular_nse(enc)
        self.assertEqual(puntaje, -1.0)   # -1 laboral

    def test_categoria_muy_bajo(self):
        from analiticas.calculos import calcular_nse
        # Forzar puntaje -5 -> Muy bajo (múltiples penalizaciones acumuladas)
        enc = self._encuesta(
            con_quien_vive='amigos',       # -1
            situacion_laboral='busco',     # -1
            dias_trabaja='no',
            tiene_cud=True,               # -1
            mudado_para_trabajar_estudiar=True,  # -1
            tiempo_viaje_puan='mas_90',    # -1  → total -5 => Muy bajo
        )
        puntaje, cat = calcular_nse(enc)
        self.assertLess(puntaje, -2.5)
        self.assertEqual(cat, 'Muy bajo')

    def test_categoria_alto(self):
        from analiticas.calculos import calcular_nse
        enc = self._encuesta(
            con_quien_vive='solo',         # +1
            dispositivos={'celular': 'individual', 'laptop': 'individual',
                          'tablet': 'individual', 'pc': 'individual'},  # +3 (pc+laptop+tablet)
            tiempo_viaje_puan='menos_30',  # +1
            hizo_uba_xxi=True,            # +1
            estudios_superiores='si_uba',
            se_recibio_uba=True,          # +1
            tiempo_en_cbc='1_2_anios',
            materias_aprobadas=3,         # +1
        )
        puntaje, cat = calcular_nse(enc)
        self.assertGreaterEqual(puntaje, 2.5)
        self.assertEqual(cat, 'Alto')


class CalcularPuntajeLogicasTests(TestCase):
    """Tests para calcular_puntaje_logicas(), réplica del notebook."""

    def _encuesta(self, silo='', cirugia_ok=None, hilera=''):
        from accounts.models import EncuestaEstudiante
        from django.contrib.auth import get_user_model
        Usuario = get_user_model()
        u = Usuario.objects.create_user(username=f'log_{id((silo, cirugia_ok, hilera))}', password='x')
        return EncuestaEstudiante.objects.create(
            estudiante=u,
            acertijo_silogismo=silo,
            acertijo_cirugia_correcto=cirugia_ok,
            acertijo_hilera=hilera,
        )

    def test_cero_con_todo_incorrecto(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_alto', False, 'rivera')
        self.assertEqual(calcular_puntaje_logicas(enc), 0)

    def test_uno_solo_silogismo(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_bajo', False, 'rivera')
        self.assertEqual(calcular_puntaje_logicas(enc), 1)

    def test_uno_solo_cirugia(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_alto', True, 'rivera')
        self.assertEqual(calcular_puntaje_logicas(enc), 1)

    def test_uno_solo_hilera(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_alto', False, 'rodriguez')
        self.assertEqual(calcular_puntaje_logicas(enc), 1)

    def test_tres_con_todo_correcto(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_bajo', True, 'rodriguez')
        self.assertEqual(calcular_puntaje_logicas(enc), 3)

    def test_cirugia_none_no_suma(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('mas_bajo', None, 'rodriguez')
        self.assertEqual(calcular_puntaje_logicas(enc), 2)  # silogismo + hilera

    def test_campos_vacios_dan_cero(self):
        from analiticas.calculos import calcular_puntaje_logicas
        enc = self._encuesta('', None, '')
        self.assertEqual(calcular_puntaje_logicas(enc), 0)


class CalcularDesenlaceParcialTests(TestCase):
    """Tests para calcular_desenlace_parcial(), réplica de pd.cut del notebook."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from cursos.models import Comision, Parcial, NotaParcial, Inscripcion
        Usuario = get_user_model()
        import datetime
        from decimal import Decimal
        docente = Usuario.objects.create_user('doc_desp', password='x', es_docente=True)
        comision = Comision.objects.create(nombre='C1')
        comision.docentes.add(docente)
        self.est = Usuario.objects.create_user('est_desp', password='x')
        self.parcial = Parcial.objects.create(
            comision=comision, cohorte=_cohorte(), nombre='P1',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('10.00'),
            umbral_aprobacion=Decimal('4.00'),
            umbral_promocion=Decimal('7.00'),
        )
        self.NotaParcial = NotaParcial

    def _nota(self, puntaje=None, ausente=False):
        n = self.NotaParcial.objects.create(
            parcial=self.parcial,
            estudiante=self.est,
            puntaje=puntaje,
            ausente=ausente,
        )
        return n

    def test_ausente_devuelve_ausente(self):
        from analiticas.calculos import calcular_desenlace_parcial
        nota = self._nota(ausente=True)
        self.assertEqual(calcular_desenlace_parcial(nota), 'Ausente')

    def test_puntaje_none_devuelve_none(self):
        from analiticas.calculos import calcular_desenlace_parcial
        nota = self._nota(puntaje=None)
        self.assertIsNone(calcular_desenlace_parcial(nota))

    def test_nota_cero_es_aplazo(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('0'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Aplazo')

    def test_nota_3_es_aplazo(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('3.00'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Aplazo')

    def test_nota_4_es_final(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('4.00'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Final')

    def test_nota_6_es_final(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('6.99'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Final')

    def test_nota_7_es_promocion(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('7.00'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Promoción')

    def test_nota_10_es_promocion(self):
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        nota = self._nota(puntaje=Decimal('10.00'))
        self.assertEqual(calcular_desenlace_parcial(nota), 'Promoción')

    def test_normaliza_escala_puntaje_total_20(self):
        """Puntaje 14/20 → normalizado 7.0 → Promoción."""
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        from cursos.models import Parcial, Comision
        import datetime
        comision = Comision.objects.create(nombre='C2')
        parcial20 = Parcial.objects.create(
            comision=comision, cohorte=_cohorte(), nombre='P2',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('20.00'),
        )
        nota = self.NotaParcial.objects.create(
            parcial=parcial20, estudiante=self.est,
            puntaje=Decimal('14.00'),
        )
        self.assertEqual(calcular_desenlace_parcial(nota), 'Promoción')

    def test_umbral_personalizado(self):
        """Umbral de aprobación 5 → nota 4.5 es Aplazo."""
        from analiticas.calculos import calcular_desenlace_parcial
        from decimal import Decimal
        from cursos.models import Parcial, Comision
        import datetime
        comision = Comision.objects.create(nombre='C3')
        p = Parcial.objects.create(
            comision=comision, cohorte=_cohorte(), nombre='P3',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('10.00'),
            umbral_aprobacion=Decimal('5.00'),
            umbral_promocion=Decimal('8.00'),
        )
        nota = self.NotaParcial.objects.create(
            parcial=p, estudiante=self.est, puntaje=Decimal('4.50'),
        )
        self.assertEqual(calcular_desenlace_parcial(nota), 'Aplazo')


class CalcularUsoPlataformaTests(TestCase):
    """Tests para calcular_uso_plataforma_antes_parcial()."""

    def setUp(self):
        import datetime
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from cursos.models import Comision, Parcial, Inscripcion
        from ejercicios.models import Ejercicio, Practica, EjercicioPractica, PracticaComision, Intento
        from django.utils import timezone

        Usuario = get_user_model()
        self.est = Usuario.objects.create_user('uso_est', password='x')
        self.docente = Usuario.objects.create_user('uso_doc', password='x', es_docente=True)
        self.comision = Comision.objects.create(nombre='C-uso')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=_cohorte())

        self.parcial = Parcial.objects.create(
            comision=self.comision, cohorte=_cohorte(), nombre='P1',
            fecha=datetime.date(2026, 6, 15),
            puntaje_total=Decimal('10.00'),
        )

        # Ejercicio y práctica
        self.ejercicio = Ejercicio.objects.create(
            enunciado='p → q',
            formula_solucion='p → q',
            tipo='formalizacion',
            creado_por=self.docente,
        )
        self.practica = Practica.objects.create(
            titulo='P', creada_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=self.practica, ejercicio=self.ejercicio, orden=1,
        )
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )

        # Fecha antes del parcial
        self.antes = timezone.make_aware(
            datetime.datetime(2026, 6, 10, 12, 0)
        )
        # Fecha después del parcial
        self.despues = timezone.make_aware(
            datetime.datetime(2026, 6, 16, 12, 0)
        )

    def _intento(self, correcto=True, cuando=None, categoria=None):
        from ejercicios.models import Intento
        from django.utils import timezone
        cuando = cuando or self.antes
        i = Intento.objects.create(
            estudiante=self.est,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            cohorte=_cohorte(),
            respuesta_raw='p → q',
            es_correcto=correcto,
            error_categoria=categoria,
        )
        # Forzar timestamp (auto_now_add no permite override directo)
        Intento.objects.filter(pk=i.pk).update(timestamp=cuando)
        i.refresh_from_db()
        return i

    def test_sin_intentos_devuelve_ceros(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['intentos_totales'], 0)
        self.assertEqual(resultado['ejercicios_distintos'], 0)
        self.assertEqual(resultado['ejercicios_resueltos'], 0)
        self.assertIsNone(resultado['tasa_exito'])
        self.assertEqual(resultado['dias_activos'], 0)

    def test_intento_posterior_no_cuenta(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        self._intento(correcto=True, cuando=self.despues)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['intentos_totales'], 0)

    def test_intento_correcto_cuenta(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        self._intento(correcto=True)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['intentos_totales'], 1)
        self.assertEqual(resultado['ejercicios_resueltos'], 1)
        self.assertEqual(resultado['tasa_exito'], 1.0)

    def test_intento_incorrecto_baja_tasa(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        import datetime
        from django.utils import timezone
        t1 = timezone.make_aware(datetime.datetime(2026, 6, 10, 10, 0))
        t2 = timezone.make_aware(datetime.datetime(2026, 6, 10, 11, 0))
        self._intento(correcto=False, cuando=t1, categoria='polaridad')
        self._intento(correcto=True, cuando=t2)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['intentos_totales'], 2)
        self.assertAlmostEqual(resultado['tasa_exito'], 0.5)
        self.assertEqual(resultado['err_polaridad'], 1)

    def test_dias_activos(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        import datetime
        from django.utils import timezone
        d1 = timezone.make_aware(datetime.datetime(2026, 6, 5, 9, 0))
        d2 = timezone.make_aware(datetime.datetime(2026, 6, 7, 9, 0))
        self._intento(cuando=d1)
        self._intento(cuando=d2)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['dias_activos'], 2)

    def test_dias_primer_y_ultimo_uso(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        import datetime
        from django.utils import timezone
        d1 = timezone.make_aware(datetime.datetime(2026, 6, 1, 9, 0))
        d2 = timezone.make_aware(datetime.datetime(2026, 6, 10, 9, 0))
        self._intento(cuando=d1)
        self._intento(cuando=d2)
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['dias_primer_uso_hasta_1p'], 14)  # 15 - 1
        self.assertEqual(resultado['dias_ultimo_uso_hasta_1p'], 5)   # 15 - 10

    def test_categorias_error_en_resultado(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        self._intento(correcto=False, categoria='tautologia')
        self._intento(correcto=False, categoria='tautologia')
        self._intento(correcto=False, categoria='polaridad')
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial)
        self.assertEqual(resultado['err_tautologia'], 2)
        self.assertEqual(resultado['err_polaridad'], 1)
        self.assertEqual(resultado['err_contradiccion'], 0)


class TrabajoVsNotaLogicaTests(TestCase):
    """analiticas.research.trabajo_vs_nota_logica"""

    def setUp(self):
        from datetime import timedelta
        from cursos.models import Parcial, NotaParcial
        from ejercicios.models import Intento as _Intento
        self.comision, self.practica, self.pc, self.ep, _ = _setup_comision('TVN', n_estudiantes=0)
        # Parcial con fecha futura para que los intentos "ahora" cuenten como previos
        self.fecha_parcial = timezone.now().date() + timedelta(days=1)
        self.parcial = Parcial.objects.create(
            comision=self.comision, cohorte=_cohorte(), nombre='Parcial 1',
            fecha=self.fecha_parcial, puntaje_total=10,
        )
        # Timestamp fijo en el pasado: garantiza que todos los intentos caen en
        # el MISMO día (dia_activos=1 para ambos), aislando solo intentos_totales
        # como indicador diferenciador. Necesario porque auto_now_add genera
        # microsegundos únicos que SQLite trata como fechas distintas en DISTINCT.
        ts_fijo = timezone.now() - timedelta(days=2)
        # est_con: consentido, trabaja mucho, nota alta
        self.est_con = _u('tvn-con', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est_con, comision=self.comision, cohorte=_cohorte())
        for ok in [True, False, False, True]:
            _intento(self.est_con, self.ep, ok, pc=self.pc)
        _Intento.objects.filter(estudiante=self.est_con).update(timestamp=ts_fijo)
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_con,
                                   nota_logica_parcial=8)
        # est_poco: consentido, trabaja poco, nota baja
        self.est_poco = _u('tvn-poco', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est_poco, comision=self.comision, cohorte=_cohorte())
        _intento(self.est_poco, self.ep, False, pc=self.pc)
        _Intento.objects.filter(estudiante=self.est_poco).update(timestamp=ts_fijo)
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_poco,
                                   nota_logica_parcial=2)
        # est_sin: SIN consentimiento → no debe aparecer
        self.est_sin = _u('tvn-sin', consentimiento_investigacion=False)
        Inscripcion.objects.create(estudiante=self.est_sin, comision=self.comision, cohorte=_cohorte())
        _intento(self.est_sin, self.ep, True, pc=self.pc)
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_sin,
                                   nota_logica_parcial=9)
        # est_ausente: consentido pero ausente → excluido
        self.est_aus = _u('tvn-aus', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est_aus, comision=self.comision, cohorte=_cohorte())
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_aus,
                                   ausente=True)
        # est_pendiente: consentido pero nota_logica None → excluido
        self.est_pend = _u('tvn-pend', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est_pend, comision=self.comision, cohorte=_cohorte())
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_pend,
                                   nota_logica_parcial=None)

    def test_filtra_consentimiento_ausente_y_pendiente(self):
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(comision_ids=[self.comision.id], solo_consentimiento=True)
        self.assertEqual(res['n'], 2)
        notas = sorted(p['nota_logica'] for p in res['puntos'])
        self.assertEqual(notas, [2.0, 8.0])

    def test_indice_trabajo_normalizado(self):
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(comision_ids=[self.comision.id], solo_consentimiento=True)
        indices = {p['nota_logica']: p['indice_trabajo'] for p in res['puntos']}
        # est_poco es el mínimo en TODOS los indicadores → índice 0.
        # Solo intentos_totales difiere en esta fixture (4 vs 1); los otros 3
        # indicadores son iguales (norma 0 para ambos) → índice de est_con = 25.0.
        self.assertEqual(indices[2.0], 0.0)
        self.assertEqual(indices[8.0], 25.0)
        self.assertGreater(indices[8.0], indices[2.0])

    def test_correlaciones_presentes(self):
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(comision_ids=[self.comision.id], solo_consentimiento=True)
        for ind in ['indice_trabajo', 'intentos_totales', 'dias_activos',
                    'ejercicios_distintos', 'practicas_abiertas']:
            self.assertIn(ind, res['correlaciones'])
            self.assertEqual(res['correlaciones'][ind]['n'], 2)
        # Con N=2 (<3) Pearson devuelve None
        self.assertIsNone(res['correlaciones']['indice_trabajo']['r_pearson'])


class CompletaronNoSeDuplicaEntreComisionesTests(TestCase):
    """Una práctica completada cuenta en su comisión, no en las dos."""

    def setUp(self):
        self.docente = _u('doc-an-dup', es_docente=True)
        self.estudiante = _u('est-an-dup')
        self.comision_a = Comision.objects.create(nombre='C-an-A')
        self.comision_b = Comision.objects.create(nombre='C-an-B')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a, cohorte=_cohorte())
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b, cohorte=_cohorte())

        self.practica = Practica.objects.create(titulo='P-an-dup', creada_por=self.docente)
        self.pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        # Completó SOLO en A.
        Progreso.objects.create(
            estudiante=self.estudiante, cohorte=_cohorte(),
            practica_comision=self.pc_a, ejercicio_practica_actual=None,
        )

    def test_mcp_estadisticas_comision_no_cuenta_la_completada_de_otra_comision(self):
        from asgiref.sync import async_to_sync

        from mcp_intentos import estadisticas_comision

        # @db_tool() envuelve la función en un wrapper async (sync_to_async
        # thread_sensitive por dentro), tal como se invoca en el resto de
        # mcp_intentos.py (ver estadisticas_comision_compat, que hace
        # `await estadisticas_comision(...)`). async_to_sync respeta el
        # thread_sensitive y corre en el mismo hilo que la conexión de la
        # TestCase; asyncio.run() lo corre en otro hilo y bloquea SQLite.
        stats_a = async_to_sync(estadisticas_comision)(self.comision_a.id)
        stats_b = async_to_sync(estadisticas_comision)(self.comision_b.id)

        self.assertEqual(stats_a['completaron_alguna_practica'], 1)
        self.assertEqual(stats_b['completaron_alguna_practica'], 0)


# ─── Tests: analíticas acotadas por cohorte ──────────────────────────────────

class AnaliticasPorCohorteTests(TestCase):
    """Las 8 funciones de analíticas no deben mezclar camadas de un recursante.

    Bug real (code review, Important I2): el spec de estas funciones pasaba
    ``estudiante_ids`` como proxy de cohorte, asumiendo que nadie pertenece a
    dos cohortes de la misma comisión. Eso es exactamente falso para un
    recursante, que es la población para la que existe la feature.

    La versión anterior de este test usaba DOS ESTUDIANTES DISTINTOS, uno por
    cohorte, y por construcción no podía detectar el bug: filtrar por
    ``estudiante_ids`` ya alcanzaba para separarlos, sin que hiciera falta
    ningún filtro de cohorte. Acá se usa el MISMO estudiante en dos cohortes
    (recursante real, mismo patrón que
    ``docentes.tests.EstudianteEditRemoveRecursanteTests`` y
    ``ejercicios.tests.RecursanteReadPathTests``): si el filtro de cohorte no
    se aplica de verdad, sus intentos de la camada vieja se cuelan al mirar
    la camada nueva.
    """

    def setUp(self):
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.comision = Comision.objects.create(nombre='IPC Noche')

        self.estudiante = _u('ana-recursa')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.c2)

        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)

        # Intentos SOLO en la cohorte vieja (c1); en c2 el mismo estudiante
        # todavía no hizo nada.
        for _ in range(4):
            Intento.objects.create(
                estudiante=self.estudiante, ejercicio_practica=self.ep, practica_comision=self.pc,
                cohorte=self.c1, respuesta_raw='q', es_correcto=False,
            )

    def test_ejercicios_dificiles_no_mezcla_cohortes_del_recursante(self):
        con_c1 = _ejercicios_mas_dificiles(
            [self.comision.id], [self.estudiante.id], min_intentos=1, cohorte_ids=[self.c1.id],
        )
        con_c2 = _ejercicios_mas_dificiles(
            [self.comision.id], [self.estudiante.id], min_intentos=1, cohorte_ids=[self.c2.id],
        )

        self.assertEqual(len(con_c1), 1)
        self.assertEqual(con_c1[0]['total'], 4)
        self.assertEqual(con_c2, [])

    def test_silencio_temprano_no_mezcla_cohortes_del_recursante(self):
        filas_c2 = _silencio_temprano([self.comision.id], [self.estudiante.id], cohorte_ids=[self.c2.id])

        self.assertEqual(len(filas_c2), 1)
        # Sin intentos en c2, el estudiante debe verse como "nunca intentó",
        # no arrastrar el último intento de c1.
        self.assertTrue(filas_c2[0]['nunca'])
        self.assertEqual(filas_c2[0]['total_intentos'], 0)

        filas_c1 = _silencio_temprano([self.comision.id], [self.estudiante.id], cohorte_ids=[self.c1.id])
        self.assertFalse(filas_c1[0]['nunca'])
        self.assertEqual(filas_c1[0]['total_intentos'], 4)

    def test_estudiantes_en_riesgo_no_mezcla_cohortes_del_recursante(self):
        en_riesgo_c1 = _estudiantes_en_riesgo(
            [self.comision.id], [self.estudiante.id], umbral_riesgo=4, cohorte_ids=[self.c1.id],
        )
        en_riesgo_c2 = _estudiantes_en_riesgo(
            [self.comision.id], [self.estudiante.id], umbral_riesgo=4, cohorte_ids=[self.c2.id],
        )

        self.assertEqual(len(en_riesgo_c1), 1)
        self.assertEqual(en_riesgo_c1[0]['racha'], 4)
        self.assertEqual(en_riesgo_c2, [])

    def test_sin_cohorte_id_preserva_el_comportamiento_agregado(self):
        """El dashboard agregado (varias comisiones, sin cohorte) no debe
        acotarse: cohorte_ids=None (default) sigue viendo todo lo del
        estudiante en la comisión, igual que antes del fix."""
        sin_cohorte = _ejercicios_mas_dificiles(
            [self.comision.id], [self.estudiante.id], min_intentos=1,
        )
        self.assertEqual(len(sin_cohorte), 1)
        self.assertEqual(sin_cohorte[0]['total'], 4)


# ─── Tests: la cohorte sale del campo, no de la fecha ────────────────────────

class CohorteExplicitaTests(TestCase):
    """La cohorte sale de Inscripcion.cohorte, no de fecha_inscripcion."""

    def test_inscripcion_tardia_conserva_su_cohorte(self):
        from cursos.models import Comision, Inscripcion
        from analiticas.research import cohortes_onboarding

        c1 = _cohorte()
        comision = Comision.objects.create(nombre='IPC Noche')
        est = _u('tardio', consentimiento_investigacion=True)
        EncuestaEstudiante.objects.create(estudiante=est)

        inscripcion = Inscripcion.objects.create(
            estudiante=est, comision=comision, cohorte=c1,
        )
        # Inscripto en noviembre: la regla vieja lo mandaría a C2.
        Inscripcion.objects.filter(pk=inscripcion.pk).update(
            fecha_inscripcion=timezone.now().replace(month=11, day=15)
        )

        filas = cohortes_onboarding([comision.id], solo_consentimiento=True)
        self.assertEqual(filas, [{'anio': 2026, 'cuatri': 1, 'count': 1}])


# ─── Tests: cohorte_ids en research.py (Task 11) ─────────────────────────────

class FiltroCohorteResearchTests(TestCase):
    """``cohorte_ids=None`` (default) agrega todas las camadas; una lista acota."""

    def setUp(self):
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.comision = Comision.objects.create(nombre='IPC Noche')

        self.est_c1 = _u('res-c1', consentimiento_investigacion=True)
        self.est_c2 = _u('res-c2', consentimiento_investigacion=True)
        _crear_encuesta(self.est_c1)
        _crear_encuesta(self.est_c2)
        Inscripcion.objects.create(estudiante=self.est_c1, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est_c2, comision=self.comision, cohorte=self.c2)

    def test_sin_cohorte_ids_devuelve_todas(self):
        from analiticas.research import perfiles_encuesta_onboarding
        filas = perfiles_encuesta_onboarding([self.comision.id])
        self.assertEqual(len(filas), 2)

    def test_cohorte_ids_acota(self):
        from analiticas.research import perfiles_encuesta_onboarding
        filas = perfiles_encuesta_onboarding([self.comision.id], cohorte_ids=[self.c1.pk])
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['cuatri'], 1)

    def test_cohorte_ids_en_funcion_de_intentos(self):
        from analiticas.research import tasa_entrada_efectiva
        sin_filtro = tasa_entrada_efectiva([self.comision.id])
        con_filtro = tasa_entrada_efectiva([self.comision.id], cohorte_ids=[self.c1.pk])
        self.assertIsInstance(sin_filtro, list)
        self.assertIsInstance(con_filtro, list)


# ─── Deuda de tests I7: dataset_intentos ciego a la cohorte (569b6d4) ────────

class DatasetIntentosRecursanteCohorteTests(TestCase):
    """``dataset_intentos`` (analiticas/anonimizador.py) debe aislar los
    intentos de un recursante por cohorte: pedir la camada actual no debe
    devolver los intentos que hizo en la camada anterior en la misma
    comisión. Antes del fix de 569b6d4, la query de Intento solo filtraba
    por ``estudiante_id__in=est_comision`` (que ya venía acotado por
    cohorte vía Inscripcion) pero no por ``Intento.cohorte`` directamente,
    así que los intentos de la camada vieja del mismo estudiante se
    colaban igual."""

    def setUp(self):
        self.comision, self.practica, self.pc, self.ep, _ = _setup_comision('dsi', n_estudiantes=0)
        self.c1 = _cohorte()  # 2026-C1, la que trae el backfill (0009)
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)

        self.estudiante = _u('dsi-recursa', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.c2)

        self.intento_c1 = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c1, respuesta_raw='p', es_correcto=True,
        )
        self.intento_c2 = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c2, respuesta_raw='q', es_correcto=False,
        )

    def test_filtro_de_cohorte_excluye_los_intentos_de_la_otra_camada(self):
        from analiticas.anonimizador import dataset_intentos
        filas = dataset_intentos([self.comision.id], anio=2027, cuatri=1)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['respuesta_raw'], 'q')

    def test_sin_filtro_devuelve_los_intentos_de_ambas_camadas(self):
        """Caso default (anio=None): no debe regresionar — siguen apareciendo
        los intentos de todas las cohortes."""
        from analiticas.anonimizador import dataset_intentos
        filas = dataset_intentos([self.comision.id])
        self.assertEqual(len(filas), 2)
        respuestas = {f['respuesta_raw'] for f in filas}
        self.assertEqual(respuestas, {'p', 'q'})


# ─── Tests: I8 — dashboard no dobla-cuenta al recursante ─────────────────────

class DashboardNoDoblesCuentaAlRecursanteTests(TestCase):
    """Code review (Important I8): ``comision.estudiantes.count()`` (M2M vía
    Inscripcion) y ``completaron_map`` (join contra
    ``estudiante__inscripciones__comision``) contaban al recursante dos
    veces, porque tiene dos filas de Inscripcion en la misma comisión (una
    por cohorte). Este dashboard agrega todas las camadas a propósito (ver
    comentario en analiticas/views.py::dashboard), así que el conteo
    correcto es "estudiantes distintos", no por cohorte — pero nunca debe
    duplicar a la misma persona."""

    def setUp(self):
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)

        self.docente = _u('doc-i8', es_docente=True, consentimiento_pedagogico=True)
        self.comision = Comision.objects.create(nombre='IPC I8')
        self.comision.docentes.add(self.docente)

        self.practica = Practica.objects.create(titulo='P-i8', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)
        ejercicio = Ejercicio.objects.create(
            enunciado='E-i8', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ejercicio, orden=1)

        self.estudiante = _u('est-i8-recursa', consentimiento_pedagogico=True)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.c2)

        # Completó la práctica en la camada actual: un único Progreso, pero
        # el join contra las dos Inscripcion lo duplicaría sin distinct.
        Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.c2,
            ejercicio_practica_actual=None,
        )

        self.client.login(username='doc-i8', password='clave123')

    def test_total_estudiantes_no_duplica_al_recursante(self):
        resp = self.client.get(reverse('analiticas:dashboard'))
        self.assertEqual(resp.status_code, 200)
        cd = resp.context['comisiones_data'][0]
        self.assertEqual(cd['total_estudiantes'], 1)

    def test_completaron_no_duplica_al_recursante(self):
        resp = self.client.get(reverse('analiticas:dashboard'))
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['completaron'], 1)


class DashboardCompletaronCuentaPersonasNoFilasDeProgresoTests(TestCase):
    """Whole-branch review: a diferencia de ``DashboardNoDoblesCuentaAlRecursanteTests``
    (donde el recursante completa la práctica en UNA sola camada y el join
    contra ``estudiante__inscripciones`` duplicaba esa única fila de
    Progreso), acá el recursante completó la práctica en las DOS camadas:
    hay dos filas de Progreso reales (una por cohorte, por el
    ``unique_together`` del modelo). El numerador de "completaron X de N"
    contaba filas de Progreso (``Count('pk', distinct=True)``) mientras el
    denominador cuenta personas (``Count('estudiante_id', distinct=True)``
    sobre Inscripcion) — unidades distintas. Resultado visible: "completaron
    2 de 1". El fix hace que el numerador también cuente personas."""

    def setUp(self):
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)

        self.docente = _u('doc-2de1', es_docente=True, consentimiento_pedagogico=True)
        self.comision = Comision.objects.create(nombre='IPC 2de1')
        self.comision.docentes.add(self.docente)

        self.practica = Practica.objects.create(titulo='P-2de1', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)
        ejercicio = Ejercicio.objects.create(
            enunciado='E-2de1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ejercicio, orden=1)

        self.estudiante = _u('est-2de1-recursa', consentimiento_pedagogico=True)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision, cohorte=self.c2)

        # Completó la práctica en AMBAS camadas: dos filas de Progreso reales
        # (una por cohorte), no un artefacto del join.
        Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.c1,
            ejercicio_practica_actual=None,
        )
        Progreso.objects.create(
            estudiante=self.estudiante, practica_comision=self.pc, cohorte=self.c2,
            ejercicio_practica_actual=None,
        )

        self.client.login(username='doc-2de1', password='clave123')

    def test_completaron_cuenta_personas_no_filas_de_progreso(self):
        resp = self.client.get(reverse('analiticas:dashboard'))
        self.assertEqual(resp.status_code, 200)
        cd = resp.context['comisiones_data'][0]
        total_estudiantes = cd['total_estudiantes']
        completaron = cd['practicas'][0]['completaron']
        self.assertEqual(total_estudiantes, 1)
        self.assertEqual(completaron, 1)
        self.assertLessEqual(completaron, total_estudiantes)


# ─── Tests: review PR #189 — hallazgo 1: primer parcial antes de cohorte ─────

class TrabajoVsNotaLogicaEligePrimerParcialDeLaCohorteTests(TestCase):
    """Code review (PR #189, hallazgo 1): ``trabajo_vs_nota_logica`` armaba
    ``primer_parcial`` con el parcial de menor fecha de TODA la comisión,
    sin filtrar por cohorte. Recién después filtraba ``notas`` por
    ``parcial__cohorte_id``. Si el parcial más antiguo de la comisión
    pertenece a otra cohorte que la pedida, ese filtro deja ``notas`` vacío
    y la función devuelve n=0 en vez de usar el primer parcial de la
    cohorte pedida."""

    def setUp(self):
        from decimal import Decimal
        from cursos.models import Parcial, NotaParcial

        self.comision, self.practica, self.pc, self.ep, _ = _setup_comision(
            'tvnp1', n_estudiantes=0,
        )
        self.c1 = _cohorte()  # 2026-C1, la del backfill
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)

        # El parcial de c1 es más viejo: sería el "primer parcial" si se
        # elige por fecha sin filtrar por cohorte primero.
        self.parcial_c1 = Parcial.objects.create(
            comision=self.comision, cohorte=self.c1, nombre='1P-c1',
            fecha=date(2026, 6, 1), puntaje_total=Decimal('10.00'),
        )
        self.parcial_c2 = Parcial.objects.create(
            comision=self.comision, cohorte=self.c2, nombre='1P-c2',
            fecha=date(2027, 6, 1), puntaje_total=Decimal('10.00'),
        )

        self.est = _u('tvnp1-est', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c2)
        NotaParcial.objects.create(
            parcial=self.parcial_c2, estudiante=self.est, nota_logica_parcial=7,
        )

    def test_usa_el_primer_parcial_de_la_cohorte_pedida(self):
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(
            comision_ids=[self.comision.id], solo_consentimiento=True,
            cohorte_ids=[self.c2.id],
        )
        self.assertEqual(res['n'], 1)
        self.assertEqual(res['puntos'][0]['nota_logica'], 7.0)


# ─── Tests: review PR #189 — hallazgo 2: uso de plataforma sin acotar cohorte ─

class CalcularUsoPlataformaAntesParcialAcotaPorCohorteTests(TestCase):
    """Code review (PR #189, hallazgo 2): ``calcular_uso_plataforma_antes_parcial``
    filtraba ``Intento`` por estudiante, comisión y fecha de corte, pero no
    por cohorte. Para un recursante, los intentos de una camada vieja
    anteriores a la fecha del parcial de la camada nueva se colaban en los
    indicadores de esfuerzo de la camada nueva."""

    def setUp(self):
        from datetime import timedelta
        from decimal import Decimal
        from cursos.models import Parcial

        self.comision, self.practica, self.pc, self.ep, _ = _setup_comision(
            'uso-cohorte', n_estudiantes=0,
        )
        self.c1 = _cohorte()
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)

        self.est = _u('uso-cohorte-recursa', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c2)

        # Fecha futura para que cualquier intento "ahora" caiga antes del corte.
        self.fecha_parcial = timezone.now().date() + timedelta(days=1)
        self.parcial_c2 = Parcial.objects.create(
            comision=self.comision, cohorte=self.c2, nombre='1P-c2',
            fecha=self.fecha_parcial, puntaje_total=Decimal('10.00'),
        )

        # Intento de la camada VIEJA (c1), anterior a la fecha del parcial de c2.
        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c1, respuesta_raw='p', es_correcto=True,
        )

    def test_no_cuenta_intentos_de_otra_cohorte(self):
        from analiticas.calculos import calcular_uso_plataforma_antes_parcial
        resultado = calcular_uso_plataforma_antes_parcial(self.est, self.parcial_c2)
        self.assertEqual(resultado['intentos_totales'], 0)


# ─── Tests: review PR #189 — hallazgo 4: demora_primer_intento duplica ───────

class DemoraPrimerIntentoNoDuplicaAlRecursanteTests(TestCase):
    """Code review (PR #189, hallazgo 4): ``demora_primer_intento`` indexaba
    ``primeros`` solo por ``estudiante``, pero ``inscriptos`` sale de
    ``Inscripcion.objects.values('estudiante_id', 'comision_id')``: un
    recursante aporta dos filas de Inscripcion en la misma comisión (una
    por cohorte), así que la función emitía dos filas idénticas de
    estudiante×práctica para la misma persona."""

    def setUp(self):
        from datetime import timedelta

        self.comision, self.practica, self.pc, self.ep, _ = _setup_comision(
            'dpi-dup', n_estudiantes=0,
        )
        self.c1 = _cohorte()
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)

        self.pc.fecha_apertura = timezone.now() - timedelta(days=10)
        self.pc.save()

        self.est = _u('dpi-dup-recursa')
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c2)

        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c2, respuesta_raw='p', es_correcto=True,
        )

    def test_no_duplica_al_recursante_sin_filtro_de_cohorte(self):
        from analiticas.research import demora_primer_intento
        filas = demora_primer_intento(self.practica.id, comision_ids=[self.comision.id])
        propias = [f for f in filas if f['estudiante_id'] == self.est.id]
        self.assertEqual(len(propias), 1)

    def test_no_duplica_al_recursante_con_varias_cohortes_pedidas(self):
        from analiticas.research import demora_primer_intento
        filas = demora_primer_intento(
            self.practica.id, comision_ids=[self.comision.id],
            cohorte_ids=[self.c1.id, self.c2.id],
        )
        propias = [f for f in filas if f['estudiante_id'] == self.est.id]
        self.assertEqual(len(propias), 1)


# ─── Tests: practicas_completadas no dobla-cuenta al recursante ─────────────

class PracticasCompletadasNoDuplicaAlRecursanteTests(TestCase):
    """``_metricas_desempeno_por_estudiante`` contaba filas de ``Progreso``
    (``Count('id')``) en vez de prácticas distintas. ``Progreso`` es único
    por (estudiante, practica_comision, cohorte): un recursante que completó
    la misma práctica en dos cohortes de la misma comisión generaba dos
    filas de Progreso para una sola práctica, así que ``practicas_completadas``
    reportaba 2 en vez de 1. Ese número alimenta ``promedio_practicas_completadas``
    en desempeno_por_nse/pandemia/puntaje_logicas, así que el recursante
    aparecía artificialmente más productivo que un no-recursante con el
    mismo trabajo real."""

    def setUp(self):
        self.comision, self.practica, self.pc, self.ep, _ = _setup_comision(
            'recursa-pc', n_estudiantes=0,
        )
        self.c1 = _cohorte()  # 2026-C1, la del backfill
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)

        self.est = _u('recursa-pc-est')
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c2)

        # _metricas_desempeno_por_estudiante arma su dict de resultado a
        # partir de Intento, no de Progreso: sin al menos un intento el
        # estudiante no aparecería en el resultado y la aserción de abajo
        # tiraría KeyError en vez de comparar el valor de practicas_completadas.
        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c2, respuesta_raw='p', es_correcto=True,
        )

        # Completó la MISMA práctica (mismo practica_comision) en las dos
        # cohortes: dos filas de Progreso, una práctica real.
        Progreso.objects.create(
            estudiante=self.est, practica_comision=self.pc, cohorte=self.c1,
            ejercicio_practica_actual=None,
        )
        Progreso.objects.create(
            estudiante=self.est, practica_comision=self.pc, cohorte=self.c2,
            ejercicio_practica_actual=None,
        )

    def test_no_duplica_practica_completada_dos_veces_por_recursante(self):
        metricas = _metricas_desempeno_por_estudiante(comision_ids=[self.comision.id])
        self.assertEqual(metricas[self.est.research_id.hex]['practicas_completadas'], 1)

    def test_la_herramienta_mcp_devuelve_el_valor_corregido(self):
        """El MCP expone `practicas_completadas` a un cliente LLM por cuatro
        herramientas que son pass-through a `analiticas.research`, así que el
        arreglo debería propagarse solo. Este test lo verifica en vez de
        asumirlo: en esta rama ya hubo una regresión que vivía entera fuera
        del app que se estaba mirando (docentes llamaba helpers de analiticas
        con el kwarg viejo y la suite de analiticas nunca lo hubiera visto).
        """
        from asgiref.sync import async_to_sync

        from mcp_intentos import perfiles_encuesta_onboarding

        _crear_encuesta(self.est)

        # @db_tool() envuelve la herramienta en un wrapper async; async_to_sync
        # respeta thread_sensitive y corre en el hilo de la TestCase (ver la
        # nota larga en EstadisticasComisionRecursanteTests).
        filas = async_to_sync(perfiles_encuesta_onboarding)(
            comision_ids=[self.comision.id],
        )

        fila = next(f for f in filas if f['pseudonimo'] == self.est.research_id.hex)
        self.assertEqual(fila['practicas_completadas'], 1)

    def test_dos_practicas_distintas_si_cuentan_por_separado(self):
        # Control: sin esta aserción, un Count de una constante también
        # pasaría el test anterior. Acá el estudiante completa una SEGUNDA
        # práctica (distinta) en la misma comisión y cohorte, y debe sumar.
        practica2 = Practica.objects.create(titulo='P-recursa-pc-2')
        pc2 = PracticaComision.objects.create(practica=practica2, comision=self.comision, orden=2)
        Progreso.objects.create(
            estudiante=self.est, practica_comision=pc2, cohorte=self.c2,
            ejercicio_practica_actual=None,
        )

        metricas = _metricas_desempeno_por_estudiante(comision_ids=[self.comision.id])
        self.assertEqual(metricas[self.est.research_id.hex]['practicas_completadas'], 2)
# ─── Tests: analiticas/filtros.py ────────────────────────────────────────────

from django.test import RequestFactory

from analiticas.filtros import cohortes_disponibles, comisiones_permitidas, resolver_filtros


class ResolverFiltrosTests(TestCase):
    """resolver_filtros es el único punto que decide qué puede ver cada usuario."""

    def setUp(self):
        self.factory = RequestFactory()
        self.com_a, _, _, _, _ = _setup_comision('FA', n_estudiantes=1)
        self.com_b, _, _, _, _ = _setup_comision('FB', n_estudiantes=1)
        self.docente_a = self.com_a.docentes.first()
        self.admin = _u('admin-filtros', is_staff=True)

    def _req(self, query='', usuario=None):
        request = self.factory.get(f'/analiticas/dashboard/?{query}')
        request.user = usuario or self.docente_a
        return request

    def test_docente_solo_ve_sus_comisiones(self):
        f = resolver_filtros(self._req())
        self.assertEqual(f.comision_ids, [self.com_a.id])

    def test_staff_ve_todas(self):
        f = resolver_filtros(self._req(usuario=self.admin))
        self.assertCountEqual(f.comision_ids, [self.com_a.id, self.com_b.id])

    def test_descarta_comision_ajena(self):
        f = resolver_filtros(self._req(f'comision_ids={self.com_a.id},{self.com_b.id}'))
        self.assertEqual(f.comision_ids, [self.com_a.id])

    def test_pedir_solo_comision_ajena_marca_seleccion_vacia(self):
        f = resolver_filtros(self._req(f'comision_ids={self.com_b.id}'))
        self.assertEqual(f.comision_ids, [])
        self.assertTrue(f.seleccion_vacia)

    def test_sin_seleccion_no_es_seleccion_vacia(self):
        f = resolver_filtros(self._req())
        self.assertFalse(f.seleccion_vacia)
        self.assertFalse(f.activo)

    def test_ids_basura_se_descartan_sin_romper(self):
        f = resolver_filtros(self._req(f'comision_ids=x,,{self.com_a.id}'))
        self.assertEqual(f.comision_ids, [self.com_a.id])

    def test_comision_ids_totalmente_irreconocible_marca_seleccion_vacia(self):
        """``?comision_ids=abc`` no debe ensanchar en silencio a "todas".

        Antes de este fix, un valor totalmente irreconocible (nada
        parseable) hacía que ``pedidas`` quedara vacía y el código lo
        confundía con "no pidió nada" -- ampliando a todas las comisiones
        permitidas. Es el mismo tipo de pedido inválido que un ID ajeno
        (`test_pedir_solo_comision_ajena_marca_seleccion_vacia`), así que
        debe dar el mismo resultado: selección explícita vacía, no "todas".
        """
        f = resolver_filtros(self._req('comision_ids=abc', usuario=self.admin))
        self.assertEqual(f.comision_ids, [])
        self.assertTrue(f.seleccion_vacia)
        # Diferenciador: sin filtro alguno (mismo usuario admin), el admin sí
        # ve ambas comisiones -- así se prueba que "abc" realmente acotó a
        # nada, y no que el admin ya vería poco de por sí.
        self.assertCountEqual(
            resolver_filtros(self._req(usuario=self.admin)).comision_ids,
            [self.com_a.id, self.com_b.id],
        )

    def test_cohorte_ids_se_parsea(self):
        cohorte = _cohorte()
        f = resolver_filtros(self._req(f'cohorte_ids={cohorte.id}'))
        self.assertEqual(f.cohorte_ids, [cohorte.id])
        self.assertTrue(f.activo)

    def test_cohorte_alias_legacy_se_traduce_a_pk(self):
        cohorte = _cohorte()
        f = resolver_filtros(self._req('cohorte=2026-1'))
        self.assertEqual(f.cohorte_ids, [cohorte.id])

    def test_sin_cohorte_es_none_no_lista_vacia(self):
        f = resolver_filtros(self._req())
        self.assertIsNone(f.cohorte_ids)

    def test_cohorte_inexistente_marca_seleccion_vacia(self):
        """Un ID de cohorte inexistente es un pedido explícito vacío, no "todas".

        Antes de este fix, ``cohorte_ids`` quedaba en ``None`` (equivalente a
        "sin filtro") -- el mismo tipo de ensanchamiento silencioso que ya
        se evitaba para comisión. Un docente que pide 2026-C1 y no existe
        debe ver "nada", no todas las camadas.
        """
        f = resolver_filtros(self._req('cohorte_ids=99999'))
        self.assertEqual(f.cohorte_ids, [])
        self.assertTrue(f.seleccion_vacia)
        # Diferenciador: sin ese filtro, la cohorte real sigue resolviendo
        # (no es que cohorte_ids=[] sea el valor por defecto de este fixture).
        self.assertEqual(
            resolver_filtros(self._req(f'cohorte_ids={_cohorte().id}')).cohorte_ids,
            [_cohorte().id],
        )

    def test_qs_incluye_comisiones_y_cohorte(self):
        cohorte = _cohorte()
        f = resolver_filtros(self._req(f'cohorte_ids={cohorte.id}'))
        self.assertIn(f'comision_ids={self.com_a.id}', f.qs)
        self.assertIn(f'cohorte_ids={cohorte.id}', f.qs)

    def test_qs_de_seleccion_vacia_no_degrada_a_todas_al_releerse(self):
        """El ``qs`` de una selección vacía debe seguir siendo "algo pedido".

        Antes de este fix, ``comision_ids=[]`` (comisión ajena) armaba
        ``qs == 'comision_ids='`` -- un valor en blanco. Releído en un
        segundo request (exactamente lo que hace el botón de exportación de
        la misma página), un parámetro en blanco se interpretaba como "no
        pidió nada" y volvía a ensanchar a "todas las permitidas": el
        docente mira el banner de "sin datos" y descarga todo. Este test
        simula ese segundo viaje de ida y vuelta.
        """
        primer_pedido = self._req(f'comision_ids={self.com_b.id}')
        f1 = resolver_filtros(primer_pedido)
        self.assertEqual(f1.comision_ids, [])
        self.assertTrue(f1.seleccion_vacia)
        # El qs no debe quedar en blanco.
        self.assertNotEqual(f1.qs, 'comision_ids=')
        self.assertNotIn('comision_ids=&', f1.qs + '&')

        # Releer ese mismo qs (como haría el link de exportación) debe
        # reproducir el mismo estado vacío -- no ensanchar a las 2 comisiones
        # que el docente sí tiene permitidas.
        segundo_pedido = self._req(f1.qs)
        f2 = resolver_filtros(segundo_pedido)
        self.assertEqual(f2.comision_ids, [])
        self.assertTrue(f2.seleccion_vacia)

    def test_qs_de_cohorte_vacia_no_degrada_a_todas_al_releerse(self):
        f1 = resolver_filtros(self._req('cohorte_ids=99999'))
        self.assertEqual(f1.cohorte_ids, [])
        self.assertTrue(f1.seleccion_vacia)
        self.assertIn('cohorte_ids=99999', f1.qs)

        f2 = resolver_filtros(self._req(f1.qs))
        self.assertEqual(f2.cohorte_ids, [])
        self.assertTrue(f2.seleccion_vacia)

    def test_cohortes_disponibles_incluye_id(self):
        opciones = cohortes_disponibles([self.com_a.id])
        self.assertEqual(opciones[0]['id'], _cohorte().id)
        self.assertEqual(opciones[0]['label'], '2026 – C1')

    def test_comisiones_permitidas_ordena_por_nombre(self):
        nombres = list(comisiones_permitidas(self.admin).values_list('nombre', flat=True))
        self.assertEqual(nombres, sorted(nombres))

    def test_acepta_checkboxes_repetidos(self):
        f = resolver_filtros(self._req(
            f'comision_ids={self.com_a.id}&comision_ids={self.com_b.id}',
            usuario=self.admin,
        ))
        self.assertCountEqual(f.comision_ids, [self.com_a.id, self.com_b.id])


# ─── Tests: calculos.py multi-comisión ───────────────────────────────────────

from analiticas.calculos import (
    _convergencia_por_ejercicio,
    _indice_atomizacion,
    _matriz_juicio_computo,
    _patron_adivinacion,
    _perfil_error_tabla,
)


class CalculosMultiComisionTests(TestCase):
    """M2–M6 pasan de una comisión a una lista, sin cambiar resultados."""

    def setUp(self):
        self.com_a, self.practica_a, self.pc_a, self.ep_a, self.est_a = _setup_comision('MA', n_estudiantes=1)
        self.com_b, self.practica_b, self.pc_b, self.ep_b, self.est_b = _setup_comision('MB', n_estudiantes=1)
        intentos_a = [_intento(self.est_a[0], self.ep_a, False, pc=self.pc_a) for _ in range(6)]
        intentos_b = [_intento(self.est_b[0], self.ep_b, False, pc=self.pc_b) for _ in range(6)]
        # _setup_comision/_u/_intento no configuran estos campos porque no son
        # su responsabilidad; sin ellos las funciones bajo prueba devuelven
        # siempre el resultado "vacío" y los tests no ejercerían el filtro
        # real de comisión/cohorte:
        #  - _patron_adivinacion exige consentimiento_pedagogico=True.
        #  - _indice_atomizacion exige diccionario_solucion no vacío para
        #    fijar n_solucion (si no, retorna temprano sin mirar comision_ids).
        #  - _patron_adivinacion descarta (criterio 3) cualquier secuencia de
        #    distancias semánticas no-creciente; como _intento() repite
        #    siempre respuesta_raw='p' (igual a formula_solucion='p'), la
        #    distancia es constante 0 y toda la secuencia queda excluida por
        #    "ya convergió". Alternamos con '~p' (distancia 2 contra 'p')
        #    para que la secuencia oscile y el criterio no la descarte.
        for est in (self.est_a[0], self.est_b[0]):
            est.consentimiento_pedagogico = True
            est.save()
        self.ep_a.ejercicio.diccionario_solucion = {'p': 'llueve'}
        self.ep_a.ejercicio.save()
        self.ep_b.ejercicio.diccionario_solucion = {'q': 'nieva'}
        self.ep_b.ejercicio.save()
        for i, intento in enumerate(intentos_a + intentos_b):
            intento.respuesta_raw = 'p' if i % 2 == 0 else '~p'
            intento.save()

        # Fixtures adicionales de tabla_verdad para _matriz_juicio_computo y
        # _perfil_error_tabla, que _indice_atomizacion/_patron_adivinacion no
        # ejercitan (filtran tipo='formalizacion'). Se agregan acá, no en un
        # fixture module-level nuevo, porque son específicas de esta clase.
        # Argumento mínimo: 1 premisa atómica + 1 conclusión negada, así la
        # tabla tiene una columna "atomica" y una "negacion" (ver
        # motor.calculos._tipo_columna) con datos reales, no triviales.
        from motor import verificar_argumento
        argumento = [
            {'formula': 'p', 'tipo': 'premisa'},
            {'formula': '~p', 'tipo': 'conclusion'},
        ]
        resultado = verificar_argumento(argumento, argumento, False)
        canonica = resultado['tabla_canonica']
        columnas_formula = [c for c in resultado['columnas_tabla']
                             if c not in resultado['variables_tabla']]

        def _crear_ejercicio_tabla_verdad(nombre, practica, pc, orden):
            ejercicio = Ejercicio.objects.create(
                enunciado=f'Argumento tv {nombre}',
                formula_solucion=_json.dumps(argumento),
                tipo='tabla_verdad',
                creado_por=None,
            )
            return EjercicioPractica.objects.create(
                practica=practica, ejercicio=ejercicio, orden=orden,
            )

        self.ep_tv_a = _crear_ejercicio_tabla_verdad('A', self.practica_a, self.pc_a, 2)
        self.ep_tv_b = _crear_ejercicio_tabla_verdad('B', self.practica_b, self.pc_b, 2)

        # Comisión A: un intento correcto (comprension_plena) y uno incorrecto
        # con un único error en la columna de la conclusión (para
        # tasa_error_por_columna real, no vacía).
        tabla_incorrecta = [dict(fila) for fila in canonica]
        tabla_incorrecta[0][columnas_formula[0]] = not tabla_incorrecta[0][columnas_formula[0]]

        Intento.objects.create(
            estudiante=self.est_a[0], ejercicio_practica=self.ep_tv_a,
            practica_comision=self.pc_a, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=True,
            juicio_estudiante=resultado['es_valido'], tabla_json=canonica,
        )
        self.intento_tv_a_incorrecto = Intento.objects.create(
            estudiante=self.est_a[0], ejercicio_practica=self.ep_tv_a,
            practica_comision=self.pc_a, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=False,
            juicio_estudiante=resultado['es_valido'], tabla_json=tabla_incorrecta,
        )
        # Comisión B: un único intento correcto, solo para que la suma de
        # ambas comisiones sea estrictamente mayor que la comisión A sola.
        Intento.objects.create(
            estudiante=self.est_b[0], ejercicio_practica=self.ep_tv_b,
            practica_comision=self.pc_b, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=True,
            juicio_estudiante=resultado['es_valido'], tabla_json=canonica,
        )

        # Fixtures para las pruebas de agregación multi-comisión de M3/M4:
        # un intento por comisión en el mismo ejercicio_id (el mismo
        # Ejercicio, referenciado por dos EjercicioPractica distintas, una
        # por practica/comisión). Sin esto, [self.com_a.id] y
        # [self.com_a.id, self.com_b.id] filtrarían el mismo ejercicio_id
        # pero sobre datos aislados por comisión (ep_a/ep_b, ep_tv_a/ep_tv_b
        # tienen ejercicio_id *distintos* cada uno), así que agregar la
        # comisión B nunca sumaría nada — exactamente indistinguible de un
        # bug que use comision_ids[0] en vez de comision_ids__in. Se
        # comparte el mismo Ejercicio (mismo ejercicio_id) entre dos
        # EjercicioPractica para que el filtro por ejercicio_id encuentre
        # intentos de ambas comisiones.
        ejercicio_tv_compartido = Ejercicio.objects.create(
            enunciado='Argumento tv compartido A/B',
            formula_solucion=_json.dumps(argumento),
            tipo='tabla_verdad',
            creado_por=None,
        )
        ep_tv_compartido_a = EjercicioPractica.objects.create(
            practica=self.practica_a, ejercicio=ejercicio_tv_compartido, orden=3,
        )
        ep_tv_compartido_b = EjercicioPractica.objects.create(
            practica=self.practica_b, ejercicio=ejercicio_tv_compartido, orden=3,
        )
        self.ejercicio_tv_compartido_id = ejercicio_tv_compartido.id
        tabla_incorrecta_b = [dict(fila) for fila in canonica]
        tabla_incorrecta_b[0][columnas_formula[0]] = not tabla_incorrecta_b[0][columnas_formula[0]]
        # juicio_estudiante=None (no resultado['es_valido']) a propósito:
        # _matriz_juicio_computo agrega TODOS los intentos tabla_verdad con
        # juicio_estudiante no nulo de la comisión, sin filtrar por
        # ejercicio_id. Si estos dos intentos llevaran juicio_estudiante
        # seteado, se sumarían a esa métrica y romperían el total pineado
        # en test_matriz_juicio_computo_dos_comisiones_agregan_ambas (ya
        # cubierto por ep_tv_a/ep_tv_b). _perfil_error_tabla no exige
        # juicio_estudiante no nulo en su filtro, así que None es seguro acá.
        Intento.objects.create(
            estudiante=self.est_a[0], ejercicio_practica=ep_tv_compartido_a,
            practica_comision=self.pc_a, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=False,
            juicio_estudiante=None, tabla_json=tabla_incorrecta_b,
        )
        Intento.objects.create(
            estudiante=self.est_b[0], ejercicio_practica=ep_tv_compartido_b,
            practica_comision=self.pc_b, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=False,
            juicio_estudiante=None, tabla_json=tabla_incorrecta_b,
        )

        ejercicio_conv_compartido = Ejercicio.objects.create(
            enunciado='Formalización compartida A/B',
            formula_solucion='p',
            tipo='formalizacion',
            creado_por=None,
        )
        ep_conv_compartido_a = EjercicioPractica.objects.create(
            practica=self.practica_a, ejercicio=ejercicio_conv_compartido, orden=4,
        )
        ep_conv_compartido_b = EjercicioPractica.objects.create(
            practica=self.practica_b, ejercicio=ejercicio_conv_compartido, orden=4,
        )
        self.ejercicio_conv_compartido_id = ejercicio_conv_compartido.id
        intentos_conv_a = [
            _intento(self.est_a[0], ep_conv_compartido_a, False, pc=self.pc_a)
            for _ in range(2)
        ]
        intentos_conv_b = [
            _intento(self.est_b[0], ep_conv_compartido_b, False, pc=self.pc_b)
            for _ in range(2)
        ]
        # Mismo motivo que para intentos_a/intentos_b más arriba: alternar
        # 'p'/'~p' evita que la secuencia de distancias sea constante 0 (lo
        # que aquí no descartaría el resultado, pero sí lo dejaría con
        # distancia_primer_intento=0 y un perfil trivial 'directo' en vez de
        # ejercitar una secuencia real).
        for i, intento in enumerate(intentos_conv_a + intentos_conv_b):
            intento.respuesta_raw = 'p' if i % 2 == 0 else '~p'
            intento.save()

    def test_una_comision_en_lista_replica_el_resultado_previo(self):
        # No-regresión del refactor: acotar a una comisión debe dar exactamente
        # lo mismo que daba la firma vieja de un solo comision_id.
        solo_a = _indice_atomizacion([self.com_a.id], self.ep_a.ejercicio_id)
        ambas = _indice_atomizacion([self.com_a.id, self.com_b.id],
                                    self.ep_a.ejercicio_id)
        # El ejercicio de A no existe en B, así que agregar B no cambia nada.
        self.assertEqual(solo_a, ambas)

    def test_comision_sin_ese_ejercicio_no_aporta(self):
        solo_b = _indice_atomizacion([self.com_b.id], self.ep_a.ejercicio_id)
        solo_a = _indice_atomizacion([self.com_a.id], self.ep_a.ejercicio_id)
        self.assertNotEqual(solo_a, solo_b)

    def test_dos_comisiones_agregan_ambas(self):
        ambas = _patron_adivinacion([self.com_a.id, self.com_b.id], min_intentos=5,
                                    max_intervalo_seg=99999)
        solo_a = _patron_adivinacion([self.com_a.id], min_intentos=5,
                                     max_intervalo_seg=99999)
        self.assertGreater(len(ambas), len(solo_a))

    def test_cohorte_inexistente_vacia_el_resultado(self):
        vacio = _patron_adivinacion([self.com_a.id], min_intentos=5,
                                    max_intervalo_seg=99999, cohorte_ids=[99999])
        self.assertEqual(vacio, [])

    def test_cohorte_none_incluye_todo(self):
        con_none = _patron_adivinacion([self.com_a.id], min_intentos=5,
                                       max_intervalo_seg=99999, cohorte_ids=None)
        self.assertGreater(len(con_none), 0)

    def test_cohorte_real_incluye_los_intentos(self):
        con_cohorte = _patron_adivinacion([self.com_a.id], min_intentos=5,
                                          max_intervalo_seg=99999,
                                          cohorte_ids=[_cohorte().id])
        self.assertGreater(len(con_cohorte), 0)

    # ─── Cobertura faltante: _matriz_juicio_computo, _convergencia_por_ejercicio,
    # _perfil_error_tabla (M2, M3, M4). Gap señalado en revisión: los 6 tests de
    # arriba solo ejercitan _indice_atomizacion (M5) y _patron_adivinacion (M6);
    # nada cubre el path multi-comisión/cohorte de las otras tres. ───────────────

    def test_matriz_juicio_computo_dos_comisiones_agregan_ambas(self):
        solo_a = _matriz_juicio_computo([self.com_a.id])
        ambas = _matriz_juicio_computo([self.com_a.id, self.com_b.id])
        self.assertGreater(ambas['total'], solo_a['total'])
        # No-trivial: solo_a ya tiene datos reales (1 comprension_plena +
        # 1 doble_obstaculo de los fixtures de tabla_verdad de setUp).
        self.assertEqual(solo_a['total'], 2)

    def test_matriz_juicio_computo_cohorte_inexistente_vacia_el_resultado(self):
        vacio = _matriz_juicio_computo([self.com_a.id], cohorte_ids=[99999])
        self.assertEqual(vacio['total'], 0)

    def test_matriz_juicio_computo_cohorte_real_incluye_los_intentos(self):
        con_none = _matriz_juicio_computo([self.com_a.id], cohorte_ids=None)
        con_cohorte = _matriz_juicio_computo([self.com_a.id], cohorte_ids=[_cohorte().id])
        self.assertGreater(con_none['total'], 0)
        self.assertEqual(con_none, con_cohorte)

    def test_perfil_error_tabla_cohorte_inexistente_vacia_el_resultado(self):
        vacio = _perfil_error_tabla(
            [self.com_a.id], self.ep_tv_a.ejercicio_id, cohorte_ids=[99999],
        )
        self.assertEqual(vacio['total_intentos_incorrectos'], 0)

    def test_perfil_error_tabla_cohorte_real_incluye_los_intentos(self):
        con_none = _perfil_error_tabla(
            [self.com_a.id], self.ep_tv_a.ejercicio_id, cohorte_ids=None,
        )
        con_cohorte = _perfil_error_tabla(
            [self.com_a.id], self.ep_tv_a.ejercicio_id, cohorte_ids=[_cohorte().id],
        )
        # No-trivial: el intento incorrecto de setUp tiene exactamente un
        # error de tabla, así que hay señal real que comparar.
        self.assertEqual(con_none['total_intentos_incorrectos'], 1)
        self.assertEqual(con_none, con_cohorte)

    def test_convergencia_por_ejercicio_cohorte_inexistente_vacia_el_resultado(self):
        vacio = _convergencia_por_ejercicio(
            [self.com_a.id], self.ep_a.ejercicio_id, cohorte_ids=[99999],
        )
        self.assertEqual(vacio['total_estudiantes'], 0)

    def test_convergencia_por_ejercicio_cohorte_real_incluye_los_intentos(self):
        con_none = _convergencia_por_ejercicio(
            [self.com_a.id], self.ep_a.ejercicio_id, cohorte_ids=None,
        )
        con_cohorte = _convergencia_por_ejercicio(
            [self.com_a.id], self.ep_a.ejercicio_id, cohorte_ids=[_cohorte().id],
        )
        # No-trivial: est_a[0] tiene 6 intentos alternando 'p'/'~p' (ver
        # setUp), lo que produce un perfil real (no un dict vacío).
        self.assertGreater(con_none['total_estudiantes'], 0)
        self.assertEqual(con_none, con_cohorte)

    def test_perfil_error_tabla_dos_comisiones_agregan_ambas(self):
        # Ambas listas apuntan al mismo ejercicio_id (ver setUp:
        # ejercicio_tv_compartido), así que si el filtro de comisión se
        # rompiera a comision_ids[0], "ambas" daría el mismo total que
        # "solo_a" en vez de sumar el intento incorrecto de comisión B.
        solo_a = _perfil_error_tabla([self.com_a.id], self.ejercicio_tv_compartido_id)
        ambas = _perfil_error_tabla([self.com_a.id, self.com_b.id],
                                    self.ejercicio_tv_compartido_id)
        self.assertEqual(solo_a['total_intentos_incorrectos'], 1)
        self.assertEqual(ambas['total_intentos_incorrectos'], 2)

    def test_convergencia_por_ejercicio_dos_comisiones_agregan_ambas(self):
        # Mismo ejercicio_id compartido entre comisiones (ver setUp:
        # ejercicio_conv_compartido); un estudiante por comisión.
        solo_a = _convergencia_por_ejercicio([self.com_a.id], self.ejercicio_conv_compartido_id)
        ambas = _convergencia_por_ejercicio([self.com_a.id, self.com_b.id],
                                            self.ejercicio_conv_compartido_id)
        self.assertEqual(solo_a['total_estudiantes'], 1)
        self.assertEqual(ambas['total_estudiantes'], 2)


# ─── Tests: helpers del dashboard con cohorte_ids ────────────────────────────

class HelpersDashboardCohorteTests(TestCase):
    """Los 8 helpers del dashboard acotan por lista de cohortes."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('HC', n_estudiantes=1)
        self.est = self.ests[0]
        for _ in range(4):
            _intento(self.est, self.ep, False, pc=self.pc)

    def test_cohorte_real_incluye_intentos(self):
        filas = _ejercicios_mas_dificiles(
            [self.com.id], [self.est.id], min_intentos=1,
            cohorte_ids=[_cohorte().id],
        )
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['total'], 4)

    def test_cohorte_inexistente_excluye_todo(self):
        filas = _ejercicios_mas_dificiles(
            [self.com.id], [self.est.id], min_intentos=1, cohorte_ids=[99999],
        )
        self.assertEqual(filas, [])

    def test_cohorte_none_incluye_todo(self):
        filas = _ejercicios_mas_dificiles(
            [self.com.id], [self.est.id], min_intentos=1, cohorte_ids=None,
        )
        self.assertEqual(filas[0]['total'], 4)

    def test_distribucion_intentos_acepta_cohorte_ids(self):
        filas = _distribucion_intentos([self.com.id], [self.est.id], cohorte_ids=[99999])
        self.assertEqual(filas, [])

    def test_evolucion_temporal_acepta_cohorte_ids(self):
        # El brief usa la clave 'intentos', pero _evolucion_temporal devuelve
        # 'total' (ver dict armado en la función); 'intentos' no existe y
        # produciría KeyError. Se corrige aquí al nombre real de campo.
        #
        # Caso positivo con valor concreto no vacío + caso negativo que
        # prueba que el filtro es lo que lo excluye (si solo se probara el
        # caso positivo, el test pasaría igual aunque el filtro de cohorte
        # nunca se aplicara — _intento() siempre usa la misma cohorte real).
        con_cohorte = _evolucion_temporal([self.com.id], [self.est.id], cohorte_ids=[_cohorte().id])
        self.assertEqual(sum(d['total'] for d in con_cohorte), 4)

        sin_cohorte = _evolucion_temporal([self.com.id], [self.est.id], cohorte_ids=[99999])
        self.assertEqual(sin_cohorte, [])

    def test_errores_sistematicos_acepta_cohorte_ids(self):
        filas = _errores_sistematicos([self.com.id], [self.est.id], min_estudiantes=1,
                                      cohorte_ids=[99999])
        self.assertEqual(filas, [])

    def test_estudiantes_en_riesgo_acepta_cohorte_ids(self):
        # Los 4 intentos incorrectos de setUp forman una racha de 4 fallos
        # consecutivos para el mismo (estudiante, EP); umbral_riesgo=4 la
        # activa exactamente.
        con_cohorte = _estudiantes_en_riesgo(
            [self.com.id], [self.est.id], umbral_riesgo=4, cohorte_ids=[_cohorte().id],
        )
        self.assertEqual(len(con_cohorte), 1)
        self.assertEqual(con_cohorte[0]['racha'], 4)

        sin_cohorte = _estudiantes_en_riesgo(
            [self.com.id], [self.est.id], umbral_riesgo=4, cohorte_ids=[99999],
        )
        self.assertEqual(sin_cohorte, [])

    def test_silencio_temprano_acepta_cohorte_ids(self):
        # _silencio_temprano siempre devuelve una fila por estudiante de la
        # población (inscripto), aunque no tenga intentos en la cohorte
        # filtrada — por eso el caso negativo no es lista vacía, sino
        # 'nunca=True' y 'total_intentos=0': eso es lo que prueba que el
        # filtro excluyó los 4 intentos reales.
        con_cohorte = _silencio_temprano([self.com.id], [self.est.id], cohorte_ids=[_cohorte().id])
        self.assertEqual(len(con_cohorte), 1)
        self.assertFalse(con_cohorte[0]['nunca'])
        self.assertEqual(con_cohorte[0]['total_intentos'], 4)

        sin_cohorte = _silencio_temprano([self.com.id], [self.est.id], cohorte_ids=[99999])
        self.assertEqual(len(sin_cohorte), 1)
        self.assertTrue(sin_cohorte[0]['nunca'])
        self.assertEqual(sin_cohorte[0]['total_intentos'], 0)

    def test_concentracion_practica_acepta_cohorte_ids(self):
        # Los 4 intentos de setUp ocurren todos "ahora" (mismo día), así que
        # dias_unicos=1 y ratio=4/1=4.0. umbral_maraton=1 los deja pasar el
        # corte (>= 3 intentos totales y ratio >= umbral) sin necesitar
        # fixtures adicionales de fechas.
        con_cohorte = _concentracion_practica(
            [self.com.id], [self.est.id], umbral_maraton=1, cohorte_ids=[_cohorte().id],
        )
        self.assertEqual(len(con_cohorte), 1)
        self.assertEqual(con_cohorte[0]['total'], 4)
        self.assertEqual(con_cohorte[0]['dias_unicos'], 1)
        self.assertEqual(con_cohorte[0]['ratio'], 4.0)

        sin_cohorte = _concentracion_practica(
            [self.com.id], [self.est.id], umbral_maraton=1, cohorte_ids=[99999],
        )
        self.assertEqual(sin_cohorte, [])

    def test_velocidad_arranque_acepta_cohorte_ids(self):
        from datetime import timedelta

        # _velocidad_arranque agrupa por (estudiante, practica), así que los
        # 4 intentos "tempranos" de self.ep en setUp (misma práctica que
        # cualquier otro EP de self.pc) contaminarían la racha de "arranque
        # tardío" de self.est si se reutiliza esa práctica. Se arma una
        # práctica nueva: un estudiante "opener" fija la apertura con un
        # intento a tiempo 0, y self.est solo tiene un intento forzado a
        # 20 días después (> umbral_arranque_dias=14) — así self.est
        # aparece como arranque tardío real, no un artefacto del fixture.
        practica2 = Practica.objects.create(titulo='P-arranque')
        pc2 = PracticaComision.objects.create(practica=practica2, comision=self.com, orden=2)
        ejercicio2 = Ejercicio.objects.create(
            enunciado='Ej arranque', formula_solucion='p', tipo='formalizacion',
        )
        ep2 = EjercicioPractica.objects.create(practica=practica2, ejercicio=ejercicio2, orden=1)

        opener = _u('est-arranque-opener')
        apertura_intento = _intento(opener, ep2, False, pc=pc2)
        tardio_intento = _intento(self.est, ep2, False, pc=pc2)
        Intento.objects.filter(pk=tardio_intento.pk).update(
            timestamp=apertura_intento.timestamp + timedelta(days=20)
        )

        con_cohorte = _velocidad_arranque(
            [self.com.id], [self.est.id, opener.id], umbral_arranque_dias=14,
            cohorte_ids=[_cohorte().id],
        )
        self.assertEqual(len(con_cohorte), 1)
        self.assertEqual(con_cohorte[0]['username'], self.est.username)
        self.assertEqual(con_cohorte[0]['intentos_total'], 1)

        sin_cohorte = _velocidad_arranque(
            [self.com.id], [self.est.id, opener.id], umbral_arranque_dias=14,
            cohorte_ids=[99999],
        )
        self.assertEqual(sin_cohorte, [])


# ─── Tests: anonimizador con cohorte_ids ─────────────────────────────────────

from analiticas.anonimizador import dataset_encuesta, dataset_intentos


class AnonimizadorCohorteIdsTests(TestCase):
    """Los datasets anonimizados aceptan cohorte_ids además de anio/cuatri."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('AN', n_estudiantes=1)
        self.est = self.ests[0]
        _crear_encuesta(self.est)
        _intento(self.est, self.ep, False, pc=self.pc)

    def test_encuesta_cohorte_real_incluye_la_fila(self):
        filas = dataset_encuesta([self.com.id], cohorte_ids=[_cohorte().id])
        self.assertEqual(len(filas), 1)

    def test_encuesta_cohorte_inexistente_vacia(self):
        filas = dataset_encuesta([self.com.id], cohorte_ids=[99999])
        self.assertEqual(filas, [])

    def test_encuesta_sin_cohorte_ids_incluye_todo(self):
        filas = dataset_encuesta([self.com.id])
        self.assertEqual(len(filas), 1)

    def test_intentos_cohorte_real_incluye_la_fila(self):
        filas = dataset_intentos([self.com.id], cohorte_ids=[_cohorte().id])
        self.assertEqual(len(filas), 1)

    def test_intentos_cohorte_inexistente_vacia(self):
        filas = dataset_intentos([self.com.id], cohorte_ids=[99999])
        self.assertEqual(filas, [])

    def test_intentos_filtra_por_cohorte_directo_no_solo_por_inscripcion(self):
        """Recursante con dos Inscripcion (cohorte c1 y c2) en la misma
        comisión y un Intento en cada cohorte. Pedir cohorte_ids=[c1.id] debe
        excluir el intento de c2 vía el filtro directo sobre Intento.cohorte
        (anonimizador.py:378), no solo vía Inscripcion.cohorte (:343).

        Distingue el caso del resto de la clase: acá est_comision NO queda
        vacío tras filtrar insc_qs (la inscripción en c1 matchea), así que la
        ejecución llega a construir `qs` y a su segundo filtro — sin esto,
        borrar la línea 378 no haría fallar ningún otro test de esta clase.
        """
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        recursante = _u('recursante-AN')
        Inscripcion.objects.create(estudiante=recursante, comision=self.com, cohorte=_cohorte())
        Inscripcion.objects.create(estudiante=recursante, comision=self.com, cohorte=c2)
        Intento.objects.create(
            estudiante=recursante, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=_cohorte(), respuesta_raw='resp-c1', es_correcto=True,
        )
        Intento.objects.create(
            estudiante=recursante, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=c2, respuesta_raw='resp-c2', es_correcto=False,
        )

        filas = dataset_intentos([self.com.id], cohorte_ids=[_cohorte().id])
        respuestas = {f['respuesta_raw'] for f in filas}
        self.assertIn('resp-c1', respuestas)
        self.assertNotIn('resp-c2', respuestas)


# ─── Tests: dashboard filtrado ───────────────────────────────────────────────

class DashboardFiltradoTests(TestCase):
    """El dashboard acota todas sus secciones por comisión y cohorte."""

    def setUp(self):
        self.com_a, _, self.pc_a, self.ep_a, self.ests_a = _setup_comision('DA', n_estudiantes=1)
        self.com_b, _, self.pc_b, self.ep_b, self.ests_b = _setup_comision('DB', n_estudiantes=1)
        self.admin = _u('admin-dash', is_staff=True, consentimiento_pedagogico=True)
        # _setup_comision no expone kwargs para el docente creado; sin este
        # consentimiento, ForzarCambioPasswordMiddleware redirige (302) a
        # /consentimientos/ antes de llegar a la vista y todos los tests que
        # loguean con este docente fallan con TypeError sobre resp.context.
        for _com in (self.com_a, self.com_b):
            for _doc in _com.docentes.all():
                _doc.consentimiento_pedagogico = True
                _doc.save(update_fields=['consentimiento_pedagogico'])
        self.c1 = _cohorte()
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        # resolver_filtros solo ofrece como opción cohortes con al menos una
        # Inscripcion real (cohortes_disponibles). Sin esta inscripción en
        # OTRA comisión, c2 no sería una cohorte "válida" y el filtro por
        # cohorte_ids=c2 se descartaría en silencio (igual que un ID
        # inexistente), volviendo a "todas" y enmascarando el bug que estos
        # tests verifican. No toca com_a, así que no afecta sus conteos.
        Inscripcion.objects.create(estudiante=self.ests_b[0], comision=self.com_b, cohorte=self.c2)
        for _ in range(3):
            _intento(self.ests_a[0], self.ep_a, False, pc=self.pc_a)
        # Un intento de la otra camada, que el filtro por c1 debe excluir.
        Intento.objects.create(
            estudiante=self.ests_a[0], ejercicio_practica=self.ep_a,
            respuesta_raw='q', es_correcto=False,
            practica_comision=self.pc_a, cohorte=self.c2,
        )
        self.client.force_login(self.admin)

    def test_sin_filtro_muestra_las_dos_comisiones(self):
        resp = self.client.get(reverse('analiticas:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['comisiones_data']), 2)

    def test_filtro_de_comision_acota_las_tarjetas(self):
        resp = self.client.get(reverse('analiticas:dashboard'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertEqual(len(resp.context['comisiones_data']), 1)
        self.assertEqual(resp.context['comisiones_data'][0]['comision'].id, self.com_a.id)

    def test_filtro_de_cohorte_excluye_intentos_de_otra_camada(self):
        resp = self.client.get(reverse('analiticas:dashboard'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(self.c1.id),
        })
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['total_intentos'], 3)

    def test_sin_filtro_de_cohorte_cuenta_las_dos_camadas(self):
        resp = self.client.get(reverse('analiticas:dashboard'),
                               {'comision_ids': str(self.com_a.id)})
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['total_intentos'], 4)

    def test_denominador_respeta_la_cohorte(self):
        # El estudiante está inscripto solo en c1: filtrar por c2 lo excluye.
        resp = self.client.get(reverse('analiticas:dashboard'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(self.c2.id),
        })
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['total_estudiantes'], 0)

    def test_recursante_no_se_cuenta_dos_veces_en_el_denominador(self):
        # Mismo estudiante inscripto en dos camadas de la MISMA comisión.
        Inscripcion.objects.create(
            estudiante=self.ests_a[0], comision=self.com_a, cohorte=self.c2,
        )
        resp = self.client.get(reverse('analiticas:dashboard'),
                               {'comision_ids': str(self.com_a.id)})
        practicas = resp.context['comisiones_data'][0]['practicas']
        # Es una persona, aunque tenga dos filas de Inscripcion.
        self.assertEqual(practicas[0]['total_estudiantes'], 1)

    def test_recursante_acotado_a_una_camada_cuenta_una_vez(self):
        Inscripcion.objects.create(
            estudiante=self.ests_a[0], comision=self.com_a, cohorte=self.c2,
        )
        resp = self.client.get(reverse('analiticas:dashboard'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(self.c2.id),
        })
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['total_estudiantes'], 1)
        # Y sus intentos son solo los de esa camada: 1, no 4.
        self.assertEqual(practicas[0]['total_intentos'], 1)

    def test_matriz_juicio_se_calcula_con_varias_comisiones(self):
        # Antes solo aparecía con exactamente una comisión.
        resp = self.client.get(reverse('analiticas:dashboard'))
        self.assertIsNotNone(resp.context['matriz_juicio'])

    def test_comision_ajena_da_estado_vacio_no_todas(self):
        docente_a = self.com_a.docentes.first()
        self.client.force_login(docente_a)
        resp = self.client.get(reverse('analiticas:dashboard'),
                               {'comision_ids': str(self.com_b.id)})
        self.assertEqual(resp.context['comisiones_data'], [])
        self.assertTrue(resp.context['filtros'].seleccion_vacia)

    def test_boton_drill_down_lleva_el_filtro_completo_en_el_html(self):
        """El botón "▶ Análisis" debe mandar cohorte_ids, no solo comisión.

        Antes de este fix, el botón se armaba con
        ``data-com="{{ comision_ids_csv }}"`` (solo comisión) y el fetch de
        ``detalle_ejercicio`` mandaba ``comision_id=`` a mano -- nunca
        cohorte_ids, aunque el endpoint sí lo acepta (Task 6). Filtrar el
        dashboard por cohorte no cambiaba lo que mostraba el drill-down: la
        fila de arriba reportaba una camada, el panel de abajo reportaba
        todas. Se prueba sobre el HTML servido -- no sobre el contexto --
        porque el bug estaba en el template, no en la vista.
        """
        resp = self.client.get(reverse('analiticas:dashboard'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(self.c1.id),
        })
        content = html.unescape(resp.content.decode())
        self.assertIn(
            f'data-qs="comision_ids={self.com_a.id}&cohorte_ids={self.c1.id}"', content,
        )
        # No debe sobrevivir ningún botón en el patrón viejo (solo comisión).
        self.assertNotIn('data-com=', content)


# ─── Tests: investigación filtrada ───────────────────────────────────────────

class InvestigacionFiltradaTests(TestCase):
    """La página de investigación acota sus métricas por comisión y cohorte."""

    def setUp(self):
        self.com_a, _, self.pc_a, self.ep_a, self.ests_a = _setup_comision('IA', n_estudiantes=1)
        self.com_b, _, self.pc_b, self.ep_b, self.ests_b = _setup_comision('IB', n_estudiantes=1)
        _crear_encuesta(self.ests_a[0])
        _crear_encuesta(self.ests_b[0])
        _intento(self.ests_a[0], self.ep_a, False, pc=self.pc_a)
        _intento(self.ests_b[0], self.ep_b, False, pc=self.pc_b)
        self.admin = _u('admin-inv', is_staff=True, consentimiento_pedagogico=True)
        # Sin este consentimiento, ForzarCambioPasswordMiddleware redirige
        # (302) a /consentimientos/ antes de llegar a la vista (ver
        # DashboardFiltradoTests, que documenta el mismo problema).
        self.client.force_login(self.admin)

    def test_sin_filtro_incluye_las_dos_comisiones(self):
        resp = self.client.get(reverse('analiticas:investigacion'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_est'], 2)

    def test_filtro_de_comision_acota_el_total(self):
        resp = self.client.get(reverse('analiticas:investigacion'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertEqual(resp.context['total_est'], 1)

    def test_filtro_de_cohorte_inexistente_vacia_las_metricas(self):
        """Una cohorte inválida es una selección explícita vacía, no "todas".

        Antes de este fix, una cohorte inexistente se descartaba en
        silencio y el filtro volvía a "todas" -- el total de estudiantes se
        quedaba en 2 en vez de caer a 0. El nombre del test ya prometía esto;
        la aserción vieja no lo probaba.
        """
        resp = self.client.get(reverse('analiticas:investigacion'),
                               {'cohorte_ids': '99999'})
        self.assertEqual(resp.context['filtros'].cohorte_ids, [])
        self.assertTrue(resp.context['filtros'].seleccion_vacia)
        self.assertEqual(resp.context['total_est'], 0)

    def test_filtro_de_cohorte_real_se_propaga(self):
        resp = self.client.get(reverse('analiticas:investigacion'),
                               {'cohorte_ids': str(_cohorte().id)})
        self.assertEqual(resp.context['filtros'].cohorte_ids, [_cohorte().id])

    def test_qs_de_exportacion_esta_en_el_contexto(self):
        resp = self.client.get(reverse('analiticas:investigacion'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertIn(f'comision_ids={self.com_a.id}', resp.context['filtros'].qs)

    def test_links_de_exportacion_llevan_el_filtro_en_el_html(self):
        """El HTML servido -- no solo el contexto -- lleva el filtro en los hrefs.

        ``test_qs_de_exportacion_esta_en_el_contexto`` solo prueba que Python
        armó el querystring; no prueba que el template lo haya usado en los
        ~51 links de exportación. Un link suelto en el patrón viejo
        (``comision_ids={{ comision_ids_csv }}``) o un typo en
        ``{{ filtros.qs }}`` no haría fallar ese test, y es exactamente el bug
        que esta tarea existe para eliminar: el docente mira una comisión y
        descarga otra.
        """
        cohorte = _cohorte()
        resp = self.client.get(reverse('analiticas:investigacion'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(cohorte.id),
        })
        # Django autoescapa el '&' interno del valor de {{ filtros.qs }}
        # (urlencode produce "comision_ids=X&cohorte_ids=Y") a '&amp;' al
        # interpolar la variable en un atributo href; el '&' literal que
        # separa "formato=csv&" en el template no se toca. Para no acoplar
        # el test a ese detalle de escaping, comparo sobre el HTML
        # desescapado en vez de sobre bytes crudos.
        content = html.unescape(resp.content.decode())
        filtro_qs = f'comision_ids={self.com_a.id}&cohorte_ids={cohorte.id}'

        # Dos secciones bien separadas del archivo (no solo la primera).
        self.assertIn(f'formato=csv&{filtro_qs}', content)
        self.assertIn(f'formato=xlsx&{filtro_qs}', content)
        self.assertIn(f'formato=ods&{filtro_qs}', content)

        # No debe sobrevivir ningún link en el patrón viejo.
        self.assertNotIn('comision_ids_csv', content)

        # Los 51 links de exportación (17 csv + 17 xlsx + 17 ods) deben llevar
        # el filtro completo -- no solo "al menos uno". Un solo link sin
        # convertir no haría fallar los tres asserts de arriba (que solo
        # piden "al menos una ocurrencia"), pero sí baja este conteo de 51.
        self.assertEqual(content.count(f'&{filtro_qs}"'), 51)

    def test_red_de_errores_usa_el_filtro_de_la_pagina_no_su_propio_selector(self):
        """El panel de red de errores ya no tiene un selector de alcance propio.

        Antes de este fix, ``investigacion.html`` tenía un ``<select>``
        separado (opciones = TODAS las comisiones permitidas, default
        "Global") que armaba su propio fetch con ``?comision_id=`` y sin
        ``cohorte_ids`` -- un segundo control de alcance que podía
        contradecir al filtro de la página (el mismo bug que Task 6 ya
        había corregido para el bloque de descarga). Ahora el panel debe
        leer el mismo ``filtros.qs`` que el resto de la pantalla.
        """
        cohorte = _cohorte()
        resp = self.client.get(reverse('analiticas:investigacion'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(cohorte.id),
        })
        content = html.unescape(resp.content.decode())
        self.assertIn(
            f'data-qs="comision_ids={self.com_a.id}&cohorte_ids={cohorte.id}"', content,
        )
        # No debe sobrevivir el selector viejo ni su fetch por comision_id.
        self.assertNotIn('red-errores-selector', content)
        self.assertNotIn("?comision_id=' + comisionId", content)


# ─── Tests: resumen de encuesta filtrado ─────────────────────────────────────

class EncuestaResumenFiltradaTests(TestCase):
    """El resumen de encuesta acota por comisión y cohorte."""

    def setUp(self):
        self.com_a, _, _, _, self.ests_a = _setup_comision('EA', n_estudiantes=1)
        self.com_b, _, _, _, self.ests_b = _setup_comision('EB', n_estudiantes=1)
        _crear_encuesta(self.ests_a[0])
        _crear_encuesta(self.ests_b[0])
        self.admin = _u('admin-enc', is_staff=True, consentimiento_pedagogico=True)
        # Sin este consentimiento, ForzarCambioPasswordMiddleware redirige
        # (302) a /consentimientos/ antes de llegar a la vista (ver
        # DashboardFiltradoTests, que documenta el mismo problema).
        self.client.force_login(self.admin)

    def test_sin_filtro_cuenta_las_dos_comisiones(self):
        resp = self.client.get(reverse('analiticas:encuesta_resumen'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_est'], 2)
        self.assertEqual(resp.context['con_encuesta'], 2)

    def test_filtro_de_comision_acota(self):
        resp = self.client.get(reverse('analiticas:encuesta_resumen'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertEqual(resp.context['total_est'], 1)

    def test_filtros_en_contexto(self):
        # No basta con "no es None": eso pasaría con cualquier objeto puesto
        # en esa clave. Se prueba que el filtro pedido efectivamente quedó
        # resuelto -- si `filtros` no viniera de resolver_filtros(request)
        # (p.ej. un objeto hardcodeado o un resolver_filtros() sin argumento)
        # este assert sobre comision_ids fallaría igual que el KeyError.
        resp = self.client.get(reverse('analiticas:encuesta_resumen'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertEqual(resp.context['filtros'].comision_ids, [self.com_a.id])

    def test_filtro_de_cohorte_acota_el_total(self):
        # _setup_comision inscribe a ambos estudiantes con la misma cohorte
        # de backfill (2026-C1, ver _cohorte()). Sin una segunda cohorte con
        # una Inscripcion real, cohortes_disponibles() no la ofrecería como
        # opción válida y el filtro se descartaría en silencio, volviendo a
        # "todas" -- lo que enmascararía un revert que no propague
        # cohorte_ids a la población ni a las métricas.
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        Inscripcion.objects.create(
            estudiante=self.ests_b[0], comision=self.com_b, cohorte=c2,
        )
        resp = self.client.get(reverse('analiticas:encuesta_resumen'),
                               {'cohorte_ids': str(c2.id)})
        self.assertEqual(resp.context['filtros'].cohorte_ids, [c2.id])
        # de las dos comisiones (2 estudiantes en total sin filtro), solo
        # est_b queda al acotar por c2.
        self.assertEqual(resp.context['total_est'], 1)


# ─── Tests: exportaciones y endpoints con filtro ─────────────────────────────

import csv as _csv
import io as _io


class ExportacionesFiltradasTests(TestCase):
    """Los exports y endpoints JSON respetan el mismo filtro que la pantalla.

    Task 6 ya hacía que los links de exportación de la pantalla de
    investigación mandaran ``cohorte_ids`` en la URL; hasta esta tarea las
    vistas que reciben esas descargas lo ignoraban por completo. Varios de
    los tests de abajo están escritos específicamente para que fallen si esa
    propagación se revierte, no solo para comprobar un 200.
    """

    def setUp(self):
        self.com_a, _, self.pc_a, self.ep_a, self.ests_a = _setup_comision('XA', n_estudiantes=1)
        self.com_b, _, self.pc_b, self.ep_b, self.ests_b = _setup_comision('XB', n_estudiantes=1)
        _crear_encuesta(self.ests_a[0])
        _crear_encuesta(self.ests_b[0])
        _intento(self.ests_a[0], self.ep_a, False, pc=self.pc_a)
        _intento(self.ests_b[0], self.ep_b, False, pc=self.pc_b)
        self.admin = _u('admin-exp', is_staff=True, consentimiento_pedagogico=True)
        # Sin este consentimiento, ForzarCambioPasswordMiddleware redirige
        # (302) a /consentimientos/ antes de llegar a la vista.
        self.client.force_login(self.admin)

    # -- descargar_investigacion (dataset=encuesta / intentos) --------------

    def test_cohorte_inexistente_vacia_la_descarga(self):
        """Una cohorte inválida es una selección explícita vacía, no "todas".

        Antes de este fix, una cohorte inexistente se descartaba en
        silencio y el filtro volvía a "todas las camadas": la fila del
        estudiante seguía en el CSV aunque se hubiera pedido una cohorte que
        no existe. Es el mismo bug que ``resolver_filtros`` corrige para
        comisión, aplicado a cohorte.
        """
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'encuesta', 'formato': 'csv',
            'comision_ids': str(self.com_a.id), 'cohorte_ids': '99999',
        })
        self.assertEqual(resp.status_code, 200)
        # Selección explícita vacía -> solo el header, ninguna fila.
        self.assertEqual(len(resp.content.decode('utf-8-sig').strip().splitlines()), 1)

    def test_descarga_encuesta_con_cohorte_real(self):
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'encuesta', 'formato': 'csv',
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(_cohorte().id),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.content.decode('utf-8-sig').strip().splitlines()), 2)

    def test_descarga_encuesta_con_otra_cohorte_excluye_la_fila(self):
        # El test anterior (y el del brief, "cohorte real") no distinguen
        # esta tarea de un revert: `_setup_comision` inscribe a est_a
        # únicamente en la cohorte de backfill (`_cohorte()`), así que pedir
        # justo esa cohorte da el mismo resultado que no filtrar nada -- el
        # código viejo (que ignora `cohorte_ids` por completo) pasaría igual.
        # Acá se prueba que pedir una cohorte REAL pero distinta (en la que
        # est_a no está inscripto) vacía la descarga -- eso sólo pasa si
        # `cohorte_ids` realmente llega hasta `dataset_encuesta`.
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        Inscripcion.objects.create(estudiante=self.ests_b[0], comision=self.com_b, cohorte=c2)
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'encuesta', 'formato': 'csv',
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(c2.id),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.content.decode('utf-8-sig').strip().splitlines()), 1)

    def test_descarga_acepta_el_alias_legacy(self):
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'encuesta', 'formato': 'csv', 'cohorte': '2026-1',
        })
        self.assertEqual(resp.status_code, 200)

    def test_descarga_alias_legacy_filtra_de_verdad(self):
        # Igual que con `cohorte_ids`: pedir el año-cuatrimestre de la
        # cohorte de backfill (la única que existe en el fixture) no
        # distingue del comportamiento sin filtrar. Se agrega una segunda
        # cohorte real con un solo inscripto para probar que el alias
        # `?cohorte=YYYY-C` de verdad acota la población.
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        Inscripcion.objects.create(estudiante=self.ests_b[0], comision=self.com_b, cohorte=c2)
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'encuesta', 'formato': 'csv', 'cohorte': '2027-1',
        })
        self.assertEqual(resp.status_code, 200)
        # Sin filtrar habría 2 filas (est_a + est_b); con el alias acotado a
        # 2027-1 sólo sobrevive la de est_b.
        self.assertEqual(len(resp.content.decode('utf-8-sig').strip().splitlines()), 2)

    def test_descarga_intentos_respeta_cohorte_ids(self):
        # c2 necesita al menos una Inscripcion real para que
        # `cohortes_disponibles` (resolver_filtros) la ofrezca como opción
        # válida -- si quedara sin inscriptos, se descartaría en silencio y
        # el pedido equivaldría a "todas" (ver advertencia del brief).
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        Inscripcion.objects.create(estudiante=self.ests_b[0], comision=self.com_b, cohorte=c2)
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'intentos', 'formato': 'csv',
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(c2.id),
        })
        self.assertEqual(resp.status_code, 200)
        # El único Intento de est_a está en la cohorte de backfill, no en
        # c2 -- filtrar por c2 debe dejar la descarga vacía (solo header).
        self.assertEqual(len(resp.content.decode('utf-8-sig').strip().splitlines()), 1)

    # -- exportar (datasets agregados de research.py) ------------------------

    def test_exportar_respeta_comision_ids(self):
        # Nota (code review): 'exportar' ya filtraba por comision_ids antes
        # de esta tarea (parseo manual con su propio 'allowed'), así que
        # este test NO falla con un revert completo de Step 5 -- el código
        # viejo también daba 2 líneas acá. Lo que sí prueba es que el
        # refactor a resolver_filtros no rompió ese comportamiento
        # preexistente. La prueba que distingue el código viejo del nuevo
        # es test_exportar_respeta_cohorte_ids (cohorte_ids es nuevo en
        # 'exportar').
        resp = self.client.get(
            reverse('analiticas:exportar', args=['entrada']),
            {'formato': 'csv', 'comision_ids': str(self.com_a.id)},
        )
        self.assertEqual(resp.status_code, 200)
        # 'entrada' devuelve una fila por PracticaComision; sin filtrar
        # habría 2 (una por comisión). Acotar a com_a deja solo 1.
        self.assertEqual(len(resp.content.decode('utf-8-sig').strip().splitlines()), 2)

    def test_exportar_respeta_cohorte_ids(self):
        # 'exportar' nunca aceptó cohorte_ids antes de esta tarea. La fila
        # de 'entrada' siempre está presente (una por práctica), así que la
        # prueba de que el filtro llegó hasta `tasa_entrada_efectiva` no es
        # el conteo de filas sino sus valores: si cohorte_ids se propaga,
        # tanto el numerador como el denominador de la tasa de entrada
        # deben caer a 0 al pedir una cohorte donde nadie de com_a está
        # inscripto. c2 necesita una Inscripcion real (en com_b) para ser
        # una opción de cohorte válida -- si no, resolver_filtros la
        # descarta en silencio y el pedido equivale a "todas".
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        Inscripcion.objects.create(estudiante=self.ests_b[0], comision=self.com_b, cohorte=c2)
        resp = self.client.get(
            reverse('analiticas:exportar', args=['entrada']),
            {'formato': 'csv', 'comision_ids': str(self.com_a.id), 'cohorte_ids': str(c2.id)},
        )
        self.assertEqual(resp.status_code, 200)
        reader = _csv.DictReader(_io.StringIO(resp.content.decode('utf-8-sig')))
        fila = next(reader)
        self.assertEqual(fila['total_estudiantes'], '0')
        self.assertEqual(fila['con_intento'], '0')

    def test_exportar_comision_ajena_da_403(self):
        """'exportar' es el único de los 4 entry points que no rechazaba una selección vacía.

        Antes de este fix, un docente que miraba el banner rojo "sin datos"
        del dashboard (comisión ajena) podía igual clickear el botón XLSX
        de esa misma pantalla y bajarse un export de TODAS sus comisiones
        permitidas -- exactamente el bug que este plan existe para eliminar.
        `descargar_investigacion`, `red_errores_json` y `detalle_ejercicio`
        ya devolvían 403/error en este caso; sólo faltaba acá.
        """
        docente_a = self.com_a.docentes.first()
        docente_a.consentimiento_pedagogico = True
        docente_a.save(update_fields=['consentimiento_pedagogico'])
        self.client.force_login(docente_a)
        resp = self.client.get(
            reverse('analiticas:exportar', args=['entrada']),
            {'formato': 'csv', 'comision_ids': str(self.com_b.id)},
        )
        self.assertEqual(resp.status_code, 403)

    def test_exportar_errores_sistematicos_respeta_cohorte_ids(self):
        """El export de 'errores_sistematicos' honra cohorte_ids igual que el dashboard.

        Bug encontrado en code review: el branch 'errores_sistematicos' de
        _datos_exportacion no usaba el dict `kw` (que ya lleva cohorte_ids
        y alimenta a los otros 16 datasets) -- a diferencia de dashboard(),
        que desde 2115bb4 sí pasa cohorte_ids a _errores_sistematicos
        (views.py, _estudiantes_dashboard). Consecuencia real: un docente
        filtraba el dashboard por cohorte, veía N errores compartidos en
        pantalla, exportaba, y el CSV traía todas las camadas.

        dashboard.html también mandaba estos export links con el patrón
        viejo `?comision_ids={{ comision_ids_csv }}` (sin cohorte alguna),
        a diferencia de investigacion.html, que usa `{{ filtros.qs }}` en
        los suyos.
        """
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        otro_est = _u('est-XA-otro-camada')
        Inscripcion.objects.create(estudiante=otro_est, comision=self.com_a, cohorte=c2)

        # ests_a[0] (cohorte de backfill) y otro_est (c2) escriben la MISMA
        # respuesta incorrecta en el mismo ejercicio/práctica -- comparten
        # el error solo si se los cuenta juntos (sin acotar por cohorte).
        Intento.objects.create(
            estudiante=self.ests_a[0], ejercicio_practica=self.ep_a, practica_comision=self.pc_a,
            cohorte=_cohorte(), respuesta_raw='error-compartido', es_correcto=False,
        )
        Intento.objects.create(
            estudiante=otro_est, ejercicio_practica=self.ep_a, practica_comision=self.pc_a,
            cohorte=c2, respuesta_raw='error-compartido', es_correcto=False,
        )

        resp_todas = self.client.get(
            reverse('analiticas:exportar', args=['errores_sistematicos']),
            {'formato': 'csv', 'comision_ids': str(self.com_a.id)},
        )
        self.assertEqual(resp_todas.status_code, 200)
        filas_todas = resp_todas.content.decode('utf-8-sig').strip().splitlines()
        # 2 estudiantes comparten la respuesta -> alcanza el umbral por
        # defecto (ConfigSitio.error_consenso_min=2) -> header + 1 fila.
        self.assertEqual(len(filas_todas), 2)

        resp_c1 = self.client.get(
            reverse('analiticas:exportar', args=['errores_sistematicos']),
            {'formato': 'csv', 'comision_ids': str(self.com_a.id), 'cohorte_ids': str(_cohorte().id)},
        )
        self.assertEqual(resp_c1.status_code, 200)
        filas_c1 = resp_c1.content.decode('utf-8-sig').strip().splitlines()
        # Acotado a la cohorte de backfill, solo 1 estudiante comparte el
        # error -- no llega al umbral y la fila desaparece (solo header).
        # Distinto del conteo sin filtrar (2 líneas arriba).
        self.assertEqual(len(filas_c1), 1)

        # El conteo exportado coincide exactamente con lo que devuelve la
        # llamada equivalente ya filtrada -- no una aproximación.
        esperado = _errores_sistematicos(
            [self.com_a.id], [self.ests_a[0].id], min_estudiantes=2,
            cohorte_ids=[_cohorte().id],
        )
        self.assertEqual(esperado, [])
        self.assertEqual(len(filas_c1) - 1, len(esperado))

    # -- red_errores_json ------------------------------------------------

    def _crear_intento_con_error(self, estudiante, ep, pc, categoria):
        return Intento.objects.create(
            estudiante=estudiante, ejercicio_practica=ep, practica_comision=pc,
            cohorte=_cohorte(), respuesta_raw='r', es_correcto=False,
            error_categoria=categoria,
        )

    def test_red_errores_acepta_comision_ids_plural(self):
        # Un par (estudiante, ejercicio) con error clasificado en cada
        # comisión: sin filtrar, n_pares=2; acotado a com_a, n_pares=1. Si
        # `comision_ids` no llegara a `red_errores`, ambas respuestas darían
        # el mismo total.
        self._crear_intento_con_error(self.ests_a[0], self.ep_a, self.pc_a, 'tautologia')
        self._crear_intento_con_error(self.ests_b[0], self.ep_b, self.pc_b, 'contradiccion')

        resp_todas = self.client.get(reverse('analiticas:red_errores'))
        self.assertEqual(resp_todas.json()['n_pares'], 2)

        resp_a = self.client.get(reverse('analiticas:red_errores'),
                                 {'comision_ids': str(self.com_a.id)})
        self.assertEqual(resp_a.json()['n_pares'], 1)

    def test_red_errores_sigue_aceptando_comision_id_singular(self):
        # Los dos consumidores JS existentes (dashboard.html,
        # practica_detail.html en realidad llaman a detalle_ejercicio, pero
        # red_errores_json siempre aceptó este alias) siguen mandando
        # `comision_id=` en singular.
        #
        # Nota (code review): red_errores_json YA aceptaba `comision_id`
        # singular antes de esta tarea (era su único parámetro, con lógica
        # ad-hoc para 'all'/int). Un revert completo de Step 3 seguiría
        # dando n_pares=1 acá por esa vía vieja -- este test no distingue
        # el código viejo del nuevo. Lo que sí prueba es que el alias sigue
        # funcionando después de migrar a resolver_filtros (no se rompió
        # al refactorizar). El caso que si es nuevo -- `comision_ids` en
        # plural -- está cubierto por test_red_errores_acepta_comision_ids_plural.
        self._crear_intento_con_error(self.ests_a[0], self.ep_a, self.pc_a, 'tautologia')
        self._crear_intento_con_error(self.ests_b[0], self.ep_b, self.pc_b, 'contradiccion')

        resp = self.client.get(reverse('analiticas:red_errores'),
                               {'comision_id': str(self.com_a.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['n_pares'], 1)

    def test_red_errores_acepta_cohorte_ids(self):
        # c2 necesita una Inscripcion real para ser una opción de cohorte
        # válida (ver advertencia del brief); si no, resolver_filtros la
        # descarta en silencio y el pedido equivale a "todas".
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        Inscripcion.objects.create(estudiante=self.ests_b[0], comision=self.com_b, cohorte=c2)
        self._crear_intento_con_error(self.ests_a[0], self.ep_a, self.pc_a, 'tautologia')

        resp = self.client.get(reverse('analiticas:red_errores'),
                               {'cohorte_ids': str(c2.id)})
        self.assertEqual(resp.status_code, 200)
        # El único par con error está en la cohorte de backfill, no en c2.
        self.assertEqual(resp.json()['n_pares'], 0)

    def test_red_errores_rechaza_comision_ajena_para_docente(self):
        # Faltaba el equivalente de test_detalle_ejercicio_rechaza_comision_
        # ajena_para_docente para este endpoint (encontrado en code review).
        # La lógica ya era correcta (seleccion_vacia -> 403), pero no
        # estaba probada -- y es la ruta de seguridad donde una regresión
        # significa que un docente lee los datos de otro.
        docente_a = self.com_a.docentes.first()
        # Sin este consentimiento, ForzarCambioPasswordMiddleware redirige
        # (302) a /consentimientos/ antes de llegar a la vista.
        docente_a.consentimiento_pedagogico = True
        docente_a.save(update_fields=['consentimiento_pedagogico'])
        self.client.force_login(docente_a)
        resp = self.client.get(reverse('analiticas:red_errores'),
                               {'comision_ids': str(self.com_b.id)})
        self.assertEqual(resp.status_code, 403)

    # -- detalle_ejercicio (M3/M4/M5) ----------------------------------------

    def test_detalle_ejercicio_acepta_cohorte_ids(self):
        resp = self.client.get(reverse('analiticas:detalle_ejercicio'), {
            'ejercicio_id': str(self.ep_a.ejercicio_id),
            'comision_ids': str(self.com_a.id),
            'cohorte_ids': str(_cohorte().id),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('convergencia', resp.json())
        # El único intento de est_a está en la cohorte de backfill, así que
        # pedirla explícitamente lo sigue incluyendo.
        self.assertEqual(resp.json()['convergencia']['total_estudiantes'], 1)

    def test_detalle_ejercicio_cohorte_distinta_vacia_la_convergencia(self):
        # Antes de esta tarea, `detalle_ejercicio` llamaba a
        # `_convergencia_por_ejercicio` con un `comision_id` escalar (Task 2
        # cambió la firma a lista) y ni siquiera aceptaba `cohorte_ids`. Este
        # test cae a 0 solo si el filtro de cohorte realmente se propaga.
        # c2 necesita una Inscripcion real para ser una opción de cohorte
        # válida (ver advertencia del brief).
        c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        Inscripcion.objects.create(estudiante=self.ests_b[0], comision=self.com_b, cohorte=c2)
        resp = self.client.get(reverse('analiticas:detalle_ejercicio'), {
            'ejercicio_id': str(self.ep_a.ejercicio_id),
            'comision_ids': str(self.com_a.id),
            'cohorte_ids': str(c2.id),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['convergencia']['total_estudiantes'], 0)

    def test_detalle_ejercicio_acepta_comision_id_singular(self):
        # Alias load-bearing: dashboard.html y practica_detail.html llaman a
        # este endpoint con `comision_id=` (singular), no `comision_ids=`.
        resp = self.client.get(reverse('analiticas:detalle_ejercicio'), {
            'ejercicio_id': str(self.ep_a.ejercicio_id),
            'comision_id': str(self.com_a.id),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['convergencia']['total_estudiantes'], 1)

    def test_detalle_ejercicio_rechaza_comision_ajena_para_docente(self):
        docente_a = self.com_a.docentes.first()
        # Sin este consentimiento, ForzarCambioPasswordMiddleware redirige
        # (302) a /consentimientos/ antes de llegar a la vista (ver
        # DashboardFiltradoTests, que documenta el mismo problema).
        docente_a.consentimiento_pedagogico = True
        docente_a.save(update_fields=['consentimiento_pedagogico'])
        self.client.force_login(docente_a)
        resp = self.client.get(reverse('analiticas:detalle_ejercicio'), {
            'ejercicio_id': str(self.ep_a.ejercicio_id),
            'comision_ids': str(self.com_b.id),
        })
        self.assertEqual(resp.status_code, 403)


# ─── Tests: MCP con comision_ids y cohorte_ids ───────────────────────────────

from mcp_intentos import _normalizar_comisiones


class MCPNormalizarComisionesTests(TestCase):
    """El alias singular y la lista nueva conviven sin ambigüedad."""

    def test_solo_singular(self):
        self.assertEqual(_normalizar_comisiones(3, None), [3])

    def test_solo_plural(self):
        self.assertEqual(_normalizar_comisiones(None, [1, 2]), [1, 2])

    def test_plural_gana_sobre_singular(self):
        self.assertEqual(_normalizar_comisiones(3, [1, 2]), [1, 2])

    def test_ninguno_es_none(self):
        self.assertIsNone(_normalizar_comisiones(None, None))

    def test_lista_vacia_es_none(self):
        self.assertIsNone(_normalizar_comisiones(None, []))

    def test_comisiones_o_todas_materializa_todas(self):
        from mcp_intentos import _comisiones_o_todas
        com, _, _, _, _ = _setup_comision('MCPT', n_estudiantes=0)
        todas = _comisiones_o_todas(None, None)
        self.assertIn(com.id, todas)


class MCPHerramientasCalculosAceptanListaTests(TestCase):
    """Las 5 herramientas MCP de calculos.py: el alias singular da el mismo
    resultado que pasar la lista explícita, y ambos coinciden con llamar al
    helper interno de analiticas.calculos directamente.

    Sin este test, un revert de la migración de las 5 herramientas (volver a
    `comision_id: int` obligatorio, pasado posicionalmente sin `_comisiones_o_todas`)
    no sería detectado por ningún otro test del plan.

    IMPORTANTE (hallazgo de revisión, corregido acá): un fixture "liviano"
    (una sola comisión, un intento correcto de formalización) satisface las
    precondiciones de datos de NINGUNA de las 4 funciones de tabla_verdad /
    atomización / adivinación de abajo, así que singular/plural/directo
    coinciden siempre en el mismo dict vacío — la comparación no prueba nada
    sobre el filtrado real de comisión. Se reutiliza acá la técnica de
    `CalculosMultiComisionTests` (arriba en este archivo):
    - M2/M4 (`_matriz_juicio_computo`, `_perfil_error_tabla`): exigen
      `tipo='tabla_verdad'`; M2 además `juicio_estudiante` no nulo, M4 además
      `tabla_json` no nulo + `es_correcto=False`. Se arma un argumento real
      con `motor.verificar_argumento` y un error de una sola celda genuino
      (no un dict/lista vacíos disfrazados de "incorrecto").
    - M5 (`_indice_atomizacion`): corta temprano si
      `ejercicio.diccionario_solucion` es falsy (default `{}`); hay que
      setearlo explícitamente.
    - M6 (`_patron_adivinacion`): exige
      `estudiante.consentimiento_pedagogico=True` (default `None`) y una
      secuencia de distancias semánticas que NO converja (si no, el criterio
      3 la descarta) — se alterna `'p'`/`'~p'` para lograrlo.

    Además, cada test agrega una segunda comisión (`self.com2`) con su
    propio fixture equivalente y verifica que el resultado "solo com" NO
    incluye los datos de `com2`, y que "ambas comisiones" sí los agrega —
    la comparación singular == plural == directo por sí sola no distingue
    un bug que ignore el filtro de comisión (siempre agrega todo) de uno
    que lo implemente bien, si ambos lados del assert usan la misma
    comisión única.
    """

    def setUp(self):
        self.com, self.practica, self.pc, self.ep, self.ests = _setup_comision(
            'MCPCALC', n_estudiantes=1,
        )
        self.com2, self.practica2, self.pc2, self.ep2, self.ests2 = _setup_comision(
            'MCPCALC2', n_estudiantes=1,
        )
        self.est = self.ests[0]
        self.est2 = self.ests2[0]

        # --- M5 (_indice_atomizacion): ejercicio de formalización
        # compartido (mismo ejercicio_id) entre ambas comisiones, con
        # diccionario_solucion no vacío.
        ejercicio_form_compartido = Ejercicio.objects.create(
            enunciado='Formalización compartida MCP', formula_solucion='p',
            tipo='formalizacion', diccionario_solucion={'p': 'llueve'},
            creado_por=None,
        )
        self.ejercicio_form_id = ejercicio_form_compartido.id
        ep_form_a = EjercicioPractica.objects.create(
            practica=self.practica, ejercicio=ejercicio_form_compartido, orden=2,
        )
        ep_form_b = EjercicioPractica.objects.create(
            practica=self.practica2, ejercicio=ejercicio_form_compartido, orden=2,
        )
        _intento(self.est, ep_form_a, True, pc=self.pc)
        _intento(self.est2, ep_form_b, True, pc=self.pc2)

        # --- M6 (_patron_adivinacion): consentimiento_pedagogico=True y
        # secuencia de distancias no convergente (alternar 'p'/'~p') para
        # no ser descartada por el criterio 3 de _hay_convergencia.
        self.est.consentimiento_pedagogico = True
        self.est.save()
        self.est2.consentimiento_pedagogico = True
        self.est2.save()
        intentos_pbv_a = [_intento(self.est, self.ep, False, pc=self.pc) for _ in range(6)]
        intentos_pbv_b = [_intento(self.est2, self.ep2, False, pc=self.pc2) for _ in range(6)]
        for i, intento in enumerate(intentos_pbv_a + intentos_pbv_b):
            intento.respuesta_raw = 'p' if i % 2 == 0 else '~p'
            intento.save()

        # --- M2/M4 (_matriz_juicio_computo, _perfil_error_tabla):
        # ejercicio tabla_verdad compartido con argumento real (mismo
        # patrón que CalculosMultiComisionTests): 1 premisa atómica + 1
        # conclusión negada, así hay columna "atomica" y "negacion" reales.
        from motor import verificar_argumento
        argumento = [
            {'formula': 'p', 'tipo': 'premisa'},
            {'formula': '~p', 'tipo': 'conclusion'},
        ]
        resultado = verificar_argumento(argumento, argumento, False)
        canonica = resultado['tabla_canonica']
        columnas_formula = [c for c in resultado['columnas_tabla']
                             if c not in resultado['variables_tabla']]
        tabla_incorrecta = [dict(fila) for fila in canonica]
        tabla_incorrecta[0][columnas_formula[0]] = not tabla_incorrecta[0][columnas_formula[0]]

        ejercicio_tv_compartido = Ejercicio.objects.create(
            enunciado='Argumento tv compartido MCP',
            formula_solucion=_json.dumps(argumento),
            tipo='tabla_verdad', creado_por=None,
        )
        self.ejercicio_tv_id = ejercicio_tv_compartido.id
        ep_tv_a = EjercicioPractica.objects.create(
            practica=self.practica, ejercicio=ejercicio_tv_compartido, orden=3,
        )
        ep_tv_b = EjercicioPractica.objects.create(
            practica=self.practica2, ejercicio=ejercicio_tv_compartido, orden=3,
        )

        # comisión 1: un correcto (comprension_plena) + un incorrecto con un
        # único error de celda.
        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=ep_tv_a,
            practica_comision=self.pc, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=True,
            juicio_estudiante=resultado['es_valido'], tabla_json=canonica,
        )
        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=ep_tv_a,
            practica_comision=self.pc, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=False,
            juicio_estudiante=resultado['es_valido'], tabla_json=tabla_incorrecta,
        )
        # comisión 2: mismo par correcto/incorrecto, sobre el MISMO
        # ejercicio_id (ep_tv_b comparte ejercicicio_tv_compartido), para
        # que el filtro de comisión en _perfil_error_tabla (que sí toma
        # ejercicio_id) tenga algo que agregar al pasar ambas comisiones.
        Intento.objects.create(
            estudiante=self.est2, ejercicio_practica=ep_tv_b,
            practica_comision=self.pc2, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=True,
            juicio_estudiante=resultado['es_valido'], tabla_json=canonica,
        )
        Intento.objects.create(
            estudiante=self.est2, ejercicio_practica=ep_tv_b,
            practica_comision=self.pc2, cohorte=_cohorte(),
            respuesta_raw=_json.dumps(argumento), es_correcto=False,
            juicio_estudiante=resultado['es_valido'], tabla_json=tabla_incorrecta,
        )

    def test_matriz_juicio_computo_alias_singular_igual_a_lista(self):
        from asgiref.sync import async_to_sync
        from mcp_intentos import matriz_juicio_computo
        from analiticas.calculos import _matriz_juicio_computo

        por_singular = async_to_sync(matriz_juicio_computo)(comision_id=self.com.id)
        por_plural = async_to_sync(matriz_juicio_computo)(comision_ids=[self.com.id])
        directo = _matriz_juicio_computo([self.com.id])

        self.assertEqual(por_singular, por_plural)
        self.assertEqual(por_singular, directo)
        # No-trivial: 1 comprension_plena + 1 doble_obstaculo reales, SOLO
        # de com (ver setUp) — el filtro excluye los de com2.
        self.assertEqual(por_singular['total'], 2)

        ambas = async_to_sync(matriz_juicio_computo)(
            comision_ids=[self.com.id, self.com2.id],
        )
        self.assertEqual(ambas['total'], 4)

    def test_convergencia_por_ejercicio_alias_singular_igual_a_lista(self):
        from asgiref.sync import async_to_sync
        from mcp_intentos import convergencia_por_ejercicio
        from analiticas.calculos import _convergencia_por_ejercicio

        por_singular = async_to_sync(convergencia_por_ejercicio)(
            ejercicio_id=self.ep.ejercicio_id, comision_id=self.com.id,
        )
        por_plural = async_to_sync(convergencia_por_ejercicio)(
            ejercicio_id=self.ep.ejercicio_id, comision_ids=[self.com.id],
        )
        directo = _convergencia_por_ejercicio([self.com.id], self.ep.ejercicio_id)

        self.assertEqual(por_singular, por_plural)
        self.assertEqual(por_singular, directo)
        # No-trivial: self.ep (ejercicio de formalización por defecto de
        # _setup_comision) es distinto entre com y com2, así que el filtro
        # de comisión ya se ejercita con datos reales aunque no comparta
        # ejercicio_id: com2 nunca podría aportar a este resultado.
        self.assertEqual(por_singular['total_estudiantes'], 1)

    def test_perfil_error_tabla_alias_singular_igual_a_lista(self):
        from asgiref.sync import async_to_sync
        from mcp_intentos import perfil_error_tabla
        from analiticas.calculos import _perfil_error_tabla

        por_singular = async_to_sync(perfil_error_tabla)(
            ejercicio_id=self.ejercicio_tv_id, comision_id=self.com.id,
        )
        por_plural = async_to_sync(perfil_error_tabla)(
            ejercicio_id=self.ejercicio_tv_id, comision_ids=[self.com.id],
        )
        directo = _perfil_error_tabla([self.com.id], self.ejercicio_tv_id)

        self.assertEqual(por_singular, por_plural)
        self.assertEqual(por_singular, directo)
        self.assertEqual(por_singular['total_intentos_incorrectos'], 1)

        ambas = async_to_sync(perfil_error_tabla)(
            ejercicio_id=self.ejercicio_tv_id,
            comision_ids=[self.com.id, self.com2.id],
        )
        self.assertEqual(ambas['total_intentos_incorrectos'], 2)

    def test_indice_atomizacion_alias_singular_igual_a_lista(self):
        from asgiref.sync import async_to_sync
        from mcp_intentos import indice_atomizacion
        from analiticas.calculos import _indice_atomizacion

        por_singular = async_to_sync(indice_atomizacion)(
            ejercicio_id=self.ejercicio_form_id, comision_id=self.com.id,
        )
        por_plural = async_to_sync(indice_atomizacion)(
            ejercicio_id=self.ejercicio_form_id, comision_ids=[self.com.id],
        )
        directo = _indice_atomizacion([self.com.id], self.ejercicio_form_id)

        self.assertEqual(por_singular, por_plural)
        self.assertEqual(por_singular, directo)
        self.assertEqual(por_singular['total_estudiantes'], 1)

        ambas = async_to_sync(indice_atomizacion)(
            ejercicio_id=self.ejercicio_form_id,
            comision_ids=[self.com.id, self.com2.id],
        )
        self.assertEqual(ambas['total_estudiantes'], 2)

    def test_patron_baja_variacion_alias_singular_igual_a_lista(self):
        from asgiref.sync import async_to_sync
        from mcp_intentos import patron_baja_variacion
        from analiticas.calculos import _patron_adivinacion

        por_singular = async_to_sync(patron_baja_variacion)(
            comision_id=self.com.id, min_intentos=5, max_intervalo_seg=99999,
        )
        por_plural = async_to_sync(patron_baja_variacion)(
            comision_ids=[self.com.id], min_intentos=5, max_intervalo_seg=99999,
        )
        directo = _patron_adivinacion(
            [self.com.id], min_intentos=5, max_intervalo_seg=99999,
        )

        self.assertEqual(por_singular, por_plural)
        self.assertEqual(por_singular, directo)
        # No-trivial: hay señal real solo para (est, ep) de com; el filtro
        # excluye la señal equivalente de com2.
        self.assertEqual(len(por_singular), 1)
        self.assertEqual(por_singular[0]['practica_titulo'], self.practica.titulo)

        ambas = async_to_sync(patron_baja_variacion)(
            comision_ids=[self.com.id, self.com2.id],
            min_intentos=5, max_intervalo_seg=99999,
        )
        self.assertEqual(len(ambas), 2)

    def test_matriz_juicio_computo_sin_comision_es_todas(self):
        # Contrato nuevo: comision_id/comision_ids ausentes ya no es un
        # TypeError por argumento faltante, sino "todas las comisiones".
        # com y com2 (setUp) ya tienen datos reales de tabla_verdad;
        # agregamos una tercera comisión SIN datos de tabla_verdad para
        # confirmar que "todas" barre efectivamente la base completa, no
        # solo un subconjunto fijo.
        com3, _p3, pc3, ep3, ests3 = _setup_comision('MCPCALC3', n_estudiantes=1)
        _intento(ests3[0], ep3, True, pc=pc3)

        from asgiref.sync import async_to_sync
        from mcp_intentos import matriz_juicio_computo
        from analiticas.calculos import _matriz_juicio_computo

        sin_filtro = async_to_sync(matriz_juicio_computo)()
        directo_todas = _matriz_juicio_computo([self.com.id, self.com2.id, com3.id])

        self.assertEqual(sin_filtro, directo_todas)
        # Si el revert volviera a exigir comision_id, esta llamada sin
        # argumentos lanzaría TypeError en vez de devolver un dict.
        self.assertEqual(sin_filtro['total'], 4)


class MCPHerramientasORMTests(TestCase):
    """Las 7 herramientas MCP de ORM directo (mcp_intentos.py) aceptan
    ``comision_ids`` y ``cohorte_ids``, con ``comision_id`` como alias
    singular heredado y ``comision_id``/``comision_ids`` ausentes = todas.

    Sigue el mismo cuidado anti-vacuidad que ``MCPHerramientasCalculosAceptanListaTests``
    (arriba): dos comisiones con datos propios y no compartidos, para que
    "solo com" vs. "com + com2" difieran de verdad, y no solo "singular ==
    plural" sobre el mismo argumento (que un filtro roto que ignore
    comisión también satisfaría).
    """

    def setUp(self):
        self.com, self.practica, self.pc, self.ep, self.ests = _setup_comision(
            'MCPORM', n_estudiantes=1,
        )
        self.com2, self.practica2, self.pc2, self.ep2, self.ests2 = _setup_comision(
            'MCPORM2', n_estudiantes=1,
        )
        self.est = self.ests[0]
        self.est2 = self.ests2[0]

        # com: 3 intentos incorrectos del mismo estudiante sobre self.ep.
        for _ in range(3):
            _intento(self.est, self.ep, False, pc=self.pc)
        # com2: 2 intentos incorrectos de otro estudiante sobre otro
        # ejercicio_practica (self.practica2 tiene un título distinto, así
        # que errores_compartidos/analizar_errores_ejercicio pueden
        # distinguir el origen de cada fila).
        for _ in range(2):
            _intento(self.est2, self.ep2, False, pc=self.pc2)

    # ─── errores_compartidos ────────────────────────────────────────────

    def test_errores_compartidos_singular_y_plural_coinciden(self):
        from mcp_intentos import errores_compartidos
        fn = errores_compartidos.fn if hasattr(errores_compartidos, 'fn') else errores_compartidos
        singular = async_to_sync(fn)(comision_id=self.com.id, min_estudiantes=1)
        plural = async_to_sync(fn)(comision_ids=[self.com.id], min_estudiantes=1)
        self.assertEqual(singular, plural)
        # No-trivial: solo la fila de com (misma respuesta 'p' en com y
        # com2, pero práctica distinta) debe aparecer.
        self.assertEqual(len(singular), 1)
        self.assertEqual(singular[0]['practica'], self.practica.titulo)

        ambas = async_to_sync(fn)(
            comision_ids=[self.com.id, self.com2.id], min_estudiantes=1,
        )
        self.assertEqual(len(ambas), 2)
        practicas = {f['practica'] for f in ambas}
        self.assertIn(self.practica2.titulo, practicas)
        # Si el filtro de comisión estuviera roto (siempre "todas"),
        # `singular` ya habría incluido la fila de com2 y el assertEqual
        # de arriba (len == 1) habría fallado.

    # ─── categorias_error_resumen ───────────────────────────────────────

    def test_categorias_error_resumen_acota_por_cohorte(self):
        from mcp_intentos import categorias_error_resumen
        fn = categorias_error_resumen.fn if hasattr(categorias_error_resumen, 'fn') else categorias_error_resumen
        vacio = async_to_sync(fn)(comision_ids=[self.com.id], cohorte_ids=[99999])
        self.assertEqual(vacio, [])

        # Con la cohorte real (la que usa `_intento` vía `_cohorte()`) hay
        # 3 intentos incorrectos de com: el filtro de cohorte no está solo
        # "apagado", realmente distingue una cohorte de otra.
        con_cohorte_real = async_to_sync(fn)(
            comision_ids=[self.com.id], cohorte_ids=[_cohorte().id],
        )
        total = sum(c['n'] for c in con_cohorte_real)
        self.assertEqual(total, 3)

    def test_categorias_error_resumen_acota_por_comision(self):
        from mcp_intentos import categorias_error_resumen
        fn = categorias_error_resumen.fn if hasattr(categorias_error_resumen, 'fn') else categorias_error_resumen
        solo_com = async_to_sync(fn)(comision_ids=[self.com.id])
        ambas = async_to_sync(fn)(comision_ids=[self.com.id, self.com2.id])
        total_solo_com = sum(c['n'] for c in solo_com)
        total_ambas = sum(c['n'] for c in ambas)
        self.assertEqual(total_solo_com, 3)
        self.assertEqual(total_ambas, 5)

    # ─── estadisticas_comision ──────────────────────────────────────────

    def test_estadisticas_comision_sin_argumentos_es_global(self):
        from mcp_intentos import estadisticas_comision
        fn = estadisticas_comision.fn if hasattr(estadisticas_comision, 'fn') else estadisticas_comision
        datos = async_to_sync(fn)()
        self.assertGreaterEqual(datos['total_intentos'], 5)
        # "Todas" no tiene una única comisión que nombrar.
        self.assertIsNone(datos['comision'])

    def test_estadisticas_comision_campo_comision_solo_con_una_sola(self):
        """El campo ``comision`` del resultado es el nombre SOLO cuando se
        pidió exactamente una comisión (por comision_id o por comision_ids
        de un solo elemento); con 0, 2+ o "todas" vale None porque ya no hay
        una única comisión que nombrar. Fija el contrato documentado en el
        docstring de la función.
        """
        from mcp_intentos import estadisticas_comision
        fn = estadisticas_comision.fn if hasattr(estadisticas_comision, 'fn') else estadisticas_comision

        por_singular = async_to_sync(fn)(comision_id=self.com.id)
        self.assertEqual(por_singular['comision'], self.com.nombre)

        por_plural_una = async_to_sync(fn)(comision_ids=[self.com.id])
        self.assertEqual(por_plural_una['comision'], self.com.nombre)
        # Distingue una comisión de otra: no es un valor fijo/hardcodeado.
        por_singular_2 = async_to_sync(fn)(comision_id=self.com2.id)
        self.assertEqual(por_singular_2['comision'], self.com2.nombre)
        self.assertNotEqual(por_singular['comision'], por_singular_2['comision'])

        por_plural_dos = async_to_sync(fn)(comision_ids=[self.com.id, self.com2.id])
        self.assertIsNone(por_plural_dos['comision'])

        sin_filtro = async_to_sync(fn)()
        self.assertIsNone(sin_filtro['comision'])

    def test_estadisticas_comision_acota_estudiantes_intentos_y_practicas(self):
        from mcp_intentos import estadisticas_comision
        fn = estadisticas_comision.fn if hasattr(estadisticas_comision, 'fn') else estadisticas_comision

        solo_com = async_to_sync(fn)(comision_ids=[self.com.id])
        self.assertEqual(solo_com['total_intentos'], 3)
        self.assertEqual(solo_com['total_estudiantes'], 1)
        self.assertEqual(len(solo_com['practicas']), 1)
        self.assertEqual(solo_com['practicas'][0]['practica'], self.practica.titulo)
        self.assertEqual(solo_com['practicas'][0]['intentos'], 3)

        ambas = async_to_sync(fn)(comision_ids=[self.com.id, self.com2.id])
        self.assertEqual(ambas['total_intentos'], 5)
        self.assertEqual(ambas['total_estudiantes'], 2)
        self.assertEqual(len(ambas['practicas']), 2)
        # Si el desglose por práctica no usara el queryset ya filtrado por
        # cohorte/comisión (`qs_intentos`) y reconstruyera desde `pc_ids`
        # sin más, este total por práctica no cambiaría con el filtro de
        # cohorte del siguiente test.

    def test_estadisticas_comision_progreso_y_cohorte(self):
        """El conteo de Progreso completado tiene FK propia a cohorte y
        debe filtrarse igual que el resto: no basta con heredar el filtro
        de comisión de PracticaComision.
        """
        from mcp_intentos import estadisticas_comision
        fn = estadisticas_comision.fn if hasattr(estadisticas_comision, 'fn') else estadisticas_comision

        cohorte_real = _cohorte()
        otra_cohorte = Cohorte.objects.create(anio=2099, cuatrimestre=1)

        Progreso.objects.create(
            estudiante=self.est, cohorte=cohorte_real,
            practica_comision=self.pc, ejercicio_practica_actual=None,
        )
        # Un intento genuino en `otra_cohorte`, sin Progreso asociado: así
        # `total_intentos` y `completaron_alguna_practica` pueden diferir en
        # esa cohorte (1 vs 0) en vez de ambos caer a 0 por casualidad, lo
        # que probaría que Progreso tiene su PROPIO filtro de cohorte y no
        # uno heredado/copiado del de `qs_intentos`.
        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=otra_cohorte,
            respuesta_raw='p', es_correcto=False,
        )

        sin_filtro = async_to_sync(fn)(comision_ids=[self.com.id])
        self.assertEqual(sin_filtro['completaron_alguna_practica'], 1)
        self.assertEqual(sin_filtro['total_intentos'], 4)

        con_cohorte_real = async_to_sync(fn)(
            comision_ids=[self.com.id], cohorte_ids=[cohorte_real.id],
        )
        self.assertEqual(con_cohorte_real['completaron_alguna_practica'], 1)
        self.assertEqual(con_cohorte_real['total_intentos'], 3)

        con_otra_cohorte = async_to_sync(fn)(
            comision_ids=[self.com.id], cohorte_ids=[otra_cohorte.id],
        )
        # El intento SÍ está en otra_cohorte (total_intentos == 1), pero el
        # Progreso completado NO (completaron == 0): si el filtro de
        # cohorte de Progreso estuviera roto (p.ej. ausente), esto
        # devolvería 1, no 0.
        self.assertEqual(con_otra_cohorte['total_intentos'], 1)
        self.assertEqual(con_otra_cohorte['completaron_alguna_practica'], 0)

    def test_estadisticas_comision_practicas_no_escala_con_la_cantidad(self):
        """El desglose por práctica no debe hacer 2 queries por PracticaComision.

        Antes de este fix, ``comision_id`` era obligatorio y ``pcs`` estaba
        acotado a una sola comisión -- el loop de 2 COUNT por vuelta era
        bounded. Ahora que es opcional ("todas" por default), llamarla sin
        argumentos recorre CADA PracticaComision de la base entera. Se
        agregan 10 prácticas más (sin relación con el fixture existente) y
        se prueba que el número de queries no crece con ellas -- si creciera
        (el bug de N+1), esta comparación fallaría por ~20 queries de más.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from mcp_intentos import estadisticas_comision
        fn = estadisticas_comision.fn if hasattr(estadisticas_comision, 'fn') else estadisticas_comision

        with CaptureQueriesContext(connection) as antes:
            datos_antes = async_to_sync(fn)()
        n_antes = len(antes.captured_queries)
        # No-vacuo: hay datos reales antes de la comparación.
        self.assertGreaterEqual(datos_antes['total_intentos'], 5)

        for i in range(10):
            p = Practica.objects.create(titulo=f'extra-{i}')
            PracticaComision.objects.create(practica=p, comision=self.com, orden=100 + i)

        with CaptureQueriesContext(connection) as despues:
            datos_despues = async_to_sync(fn)()
        n_despues = len(despues.captured_queries)

        # Las 10 prácticas nuevas SÍ deben aparecer en el desglose (si no,
        # esta comparación de queries sería trivial: "0 queries más para 0
        # prácticas más").
        self.assertEqual(len(datos_despues['practicas']), len(datos_antes['practicas']) + 10)
        self.assertEqual(n_antes, n_despues)

    # ─── intentos_por_estudiante ────────────────────────────────────────

    def test_intentos_por_estudiante_acota_por_comision_y_cohorte(self):
        from mcp_intentos import intentos_por_estudiante
        fn = intentos_por_estudiante.fn if hasattr(intentos_por_estudiante, 'fn') else intentos_por_estudiante
        pseudonimo = self.est.research_id.hex

        sin_filtro = async_to_sync(fn)(pseudonimo=pseudonimo)
        self.assertEqual(len(sin_filtro), 3)

        solo_com = async_to_sync(fn)(pseudonimo=pseudonimo, comision_ids=[self.com.id])
        self.assertEqual(len(solo_com), 3)

        con_cohorte_real = async_to_sync(fn)(
            pseudonimo=pseudonimo, cohorte_ids=[_cohorte().id],
        )
        self.assertEqual(len(con_cohorte_real), 3)

        con_otra_comision = async_to_sync(fn)(pseudonimo=pseudonimo, comision_ids=[self.com2.id])
        self.assertEqual(con_otra_comision, [])
        # `self.est` nunca participó de com2: si el filtro de comisión
        # estuviera roto (p.ej. ignorado), esto devolvería los 3 intentos
        # igual que `sin_filtro`.

    # ─── buscar_respuesta ───────────────────────────────────────────────

    def test_buscar_respuesta_acota_por_comision(self):
        from mcp_intentos import buscar_respuesta
        fn = buscar_respuesta.fn if hasattr(buscar_respuesta, 'fn') else buscar_respuesta

        todas = async_to_sync(fn)(texto='p')
        self.assertEqual(len(todas), 5)

        solo_com = async_to_sync(fn)(texto='p', comision_ids=[self.com.id])
        self.assertEqual(len(solo_com), 3)
        for r in solo_com:
            self.assertEqual(r['estudiante'], self.est.research_id.hex)

        solo_com2 = async_to_sync(fn)(texto='p', comision_id=self.com2.id)
        self.assertEqual(len(solo_com2), 2)

    # ─── analizar_errores_ejercicio ─────────────────────────────────────

    def test_analizar_errores_ejercicio_acota_por_comision(self):
        from mcp_intentos import analizar_errores_ejercicio
        fn = analizar_errores_ejercicio.fn if hasattr(analizar_errores_ejercicio, 'fn') else analizar_errores_ejercicio

        # self.ep y self.ep2 apuntan a ejercicios distintos (uno por
        # `_setup_comision`), así que filtrar por ejercicio_id ya acota a
        # uno de los dos grupos; el filtro de comisión debe coincidir.
        solo_com = async_to_sync(fn)(
            ejercicio_id=self.ep.ejercicio_id, comision_ids=[self.com.id],
        )
        self.assertEqual(solo_com['total_intentos'], 3)

        # Pedir una comisión que no tiene ese ejercicio da 0, no un error:
        # confirma que el filtro de comisión se aplica de verdad (y no que
        # el resultado ya viniera acotado solo por ejercicio_id).
        otra_comision = async_to_sync(fn)(
            ejercicio_id=self.ep.ejercicio_id, comision_ids=[self.com2.id],
        )
        self.assertEqual(otra_comision['total_intentos'], 0)

    # ─── listar_intentos / _listar_intentos_impl ───────────────────────

    def test_listar_intentos_acota_por_comision_y_cohorte(self):
        from mcp_intentos import listar_intentos
        fn = listar_intentos.fn if hasattr(listar_intentos, 'fn') else listar_intentos

        sin_filtro = async_to_sync(fn)(limit=100)
        self.assertEqual(len(sin_filtro), 5)

        solo_com = async_to_sync(fn)(comision_ids=[self.com.id], limit=100)
        self.assertEqual(len(solo_com), 3)
        for r in solo_com:
            self.assertEqual(r['comision'], self.com.nombre)

        con_cohorte_falsa = async_to_sync(fn)(
            comision_ids=[self.com.id], cohorte_ids=[99999], limit=100,
        )
        self.assertEqual(con_cohorte_falsa, [])

    def test_listar_intentos_compat_reenvia_comision_ids_y_cohorte_ids(self):
        """listar_intentos_compat NO splatea genericamente (a diferencia de
        los otros seis wrappers *_compat): arma a mano el dict de kwargs que
        reenvia a _listar_intentos_impl. Si alguien agrega un parametro
        nuevo a listar_intentos sin tocar tambien este allowlist, un cliente
        que llame por esta via recibe resultados SIN FILTRAR en silencio
        (sin error), que es exactamente el modo de falla que este plan viene
        cazando. Este test pasa comision_ids/cohorte_ids en la forma
        {"kwargs": {...}} (el shape real de un conector externo) y exige que
        el corte sea real: com2 tiene datos propios que NO deben aparecer.
        """
        from mcp_intentos import listar_intentos_compat
        fn = listar_intentos_compat.fn if hasattr(listar_intentos_compat, 'fn') else listar_intentos_compat

        solo_com = async_to_sync(fn)(kwargs={
            'comision_ids': [self.com.id],
            'cohorte_ids': [_cohorte().id],
            'limit': 100,
        })
        # No-trivial: si el wrapper dropeara comision_ids/cohorte_ids (el bug
        # que motiva este test), esto devolveria los 5 intentos de ambas
        # comisiones, no los 3 de `com`.
        self.assertEqual(len(solo_com), 3)
        for r in solo_com:
            self.assertEqual(r['comision'], self.com.nombre)

        con_cohorte_falsa = async_to_sync(fn)(kwargs={
            'comision_ids': [self.com.id],
            'cohorte_ids': [99999],
            'limit': 100,
        })
        self.assertEqual(con_cohorte_falsa, [])


# ─── Tests: URLs de ejercicio para los gráficos ──────────────────────────────

from analiticas.views import _url_ejercicio, _urls_ejercicios


class UrlsEjercicioParaGraficosTests(TestCase):
    """Los gráficos necesitan la URL resuelta en el servidor: reconstruir la
    ruta de Django en JavaScript se rompería en silencio ante un cambio de
    ``ejercicios/urls.py`` — el link seguiría existiendo, apuntando a nada."""

    def setUp(self):
        self.com_a, self.practica, self.pc_a, self.ep, _ = _setup_comision('URL-A')
        # La MISMA práctica asignada a una segunda comisión: es el caso que
        # obliga a una regla determinística, porque el ep tiene dos pc.
        self.com_b = Comision.objects.create(nombre='URL-B')
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.com_b, orden=1,
        )

    def test_arma_la_ruta_con_pc_y_ep(self):
        url = _url_ejercicio(self.pc_a.id, self.ep.id)
        self.assertEqual(url, f'/practica/{self.pc_a.id}/ejercicio/{self.ep.id}/')

    def test_sin_pc_devuelve_none(self):
        self.assertIsNone(_url_ejercicio(None, self.ep.id))

    def test_bulk_resuelve_el_ep(self):
        urls = _urls_ejercicios([self.ep.id], [self.com_a.id])
        self.assertEqual(urls[self.ep.id], f'/practica/{self.pc_a.id}/ejercicio/{self.ep.id}/')

    def test_bulk_con_dos_comisiones_elige_el_pc_menor_y_es_estable(self):
        menor = min(self.pc_a.id, self.pc_b.id)
        ids = [self.com_a.id, self.com_b.id]
        primera = _urls_ejercicios([self.ep.id], ids)
        segunda = _urls_ejercicios([self.ep.id], list(reversed(ids)))
        self.assertEqual(primera[self.ep.id], f'/practica/{menor}/ejercicio/{self.ep.id}/')
        # Estable: el orden de comision_ids no puede cambiar el link.
        self.assertEqual(primera, segunda)

    def test_bulk_sin_comision_visible_devuelve_none(self):
        otra = Comision.objects.create(nombre='URL-ajena')
        urls = _urls_ejercicios([self.ep.id], [otra.id])
        self.assertIsNone(urls[self.ep.id])

    def test_bulk_no_hace_una_query_por_ejercicio(self):
        # Estos gráficos traen ~40 filas; resolver de a una sería N+1.
        ep2 = EjercicioPractica.objects.create(
            practica=self.practica,
            ejercicio=Ejercicio.objects.create(
                enunciado='Otro', formula_solucion='q', tipo='formalizacion',
                creado_por=self.com_a.docentes.first(),
            ),
            orden=2,
        )
        with self.assertNumQueries(1):
            _urls_ejercicios([self.ep.id, ep2.id], [self.com_a.id])


# ─── Tests: filas de C1/B2/D1 llevan la url del ejercicio ────────────────────

class InvestigacionGraficosLlevanUrlTests(TestCase):
    """Las tablas de C1/B2/D1 ya enlazaban al ejercicio; los gráficos no."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('GRAF-INV', n_estudiantes=1)
        self.est = self.ests[0]
        _crear_encuesta(self.est)
        # Un fallo y luego un acierto: aparece en las tres secciones.
        _intento(self.est, self.ep, False, pc=self.pc)
        _intento(self.est, self.ep, True, pc=self.pc)
        self.admin = _u('admin-graf-inv', is_staff=True, consentimiento_pedagogico=True)
        self.client.force_login(self.admin)

    def test_las_tres_secciones_traen_url(self):
        resp = self.client.get(reverse('analiticas:investigacion'))
        esperada = f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/'
        for clave in ('intentos', 'persistencia', 'abandono'):
            filas = resp.context[clave]
            self.assertTrue(filas, f'{clave} vino vacío: el test no probaría nada')
            self.assertEqual(filas[0]['url'], esperada, f'falla en {clave}')

    def test_la_url_llega_al_html_servido(self):
        # Sobre resp.content, no sobre el contexto: el JSON del gráfico se
        # serializa con json_script y es lo que realmente consume Chart.js.
        # OJO: la tabla de la misma sección ya renderiza esta URL en su
        # <a href> (usa pc_id/ep_id con {% url %}), así que buscarla en
        # cualquier parte de la página sería vacuo: pasaría igual aunque
        # _enrich no le agregara 'url' al dict. Hay que mirar puntualmente
        # adentro de cada <script id="data-...">, que es lo que Chart.js lee.
        resp = self.client.get(reverse('analiticas:investigacion'))
        cuerpo = resp.content.decode('utf-8')
        esperada = f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/'
        for data_id in ('data-intentos', 'data-persistencia', 'data-abandono'):
            bloque = re.search(rf'<script id="{data_id}"[^>]*>(.*?)</script>', cuerpo, re.DOTALL)
            self.assertIsNotNone(bloque, f'no se encontró el bloque {data_id}')
            self.assertIn(esperada, bloque.group(1), f'falla en {data_id}')


# ─── Tests: los dos paneles por ejercicio del dashboard llevan ep_id/url ─────

class DashboardGraficosLlevanUrlTests(TestCase):
    """Los dos paneles por ejercicio del dashboard: difíciles y distribución."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('GRAF-DASH', n_estudiantes=1)
        self.est = self.ests[0]
        _intento(self.est, self.ep, False, pc=self.pc)
        _intento(self.est, self.ep, True, pc=self.pc)

    def test_ejercicios_dificiles_trae_ep_id_y_url(self):
        filas = _ejercicios_mas_dificiles([self.com.id], [self.est.id], min_intentos=1)
        self.assertTrue(filas, 'sin filas el test no probaría nada')
        self.assertEqual(filas[0]['ep_id'], self.ep.id)
        self.assertEqual(
            filas[0]['url'], f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/',
        )

    def test_distribucion_intentos_trae_ep_id_y_url(self):
        filas = _distribucion_intentos([self.com.id], [self.est.id])
        self.assertTrue(filas, 'sin filas el test no probaría nada')
        self.assertEqual(filas[0]['ep_id'], self.ep.id)
        self.assertEqual(
            filas[0]['url'], f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/',
        )

    def test_distribucion_elige_un_ep_estable_cuando_el_ejercicio_esta_en_dos(self):
        # _distribucion_intentos agrupa por ejercicio_id, no por ep_id: el mismo
        # ejercicio en dos prácticas es UNA fila que cubre dos EP. El link tiene
        # que ser el mismo entre cargas.
        practica2 = Practica.objects.create(titulo='P-GRAF-DASH-2')
        pc2 = PracticaComision.objects.create(
            practica=practica2, comision=self.com, orden=2,
        )
        ep2 = EjercicioPractica.objects.create(
            practica=practica2, ejercicio=self.ep.ejercicio, orden=1,
        )
        _intento(self.est, ep2, True, pc=pc2)

        filas = _distribucion_intentos([self.com.id], [self.est.id])
        fila = next(f for f in filas if f['ep_id'] in (self.ep.id, ep2.id))
        self.assertEqual(fila['ep_id'], min(self.ep.id, ep2.id))
        self.assertEqual(fila, next(
            f for f in _distribucion_intentos([self.com.id], [self.est.id])
            if f['ep_id'] in (self.ep.id, ep2.id)
        ))

    def test_ejercicio_sin_comision_visible_deja_url_none(self):
        # El helper recibe una comisión que no contiene a este ejercicio.
        otra = Comision.objects.create(nombre='GRAF-DASH-ajena')
        filas = _ejercicios_mas_dificiles([self.com.id], [self.est.id], min_intentos=1)
        urls = _urls_ejercicios([f['ep_id'] for f in filas], [otra.id])
        self.assertIsNone(urls[self.ep.id])

    def test_distribucion_muestra_la_practica_del_ep_que_enlaza(self):
        # Regresión: _distribucion_intentos agrupa por ejercicio_id y elegía
        # la metadata (practica_titulo/enunciado) del primer EP iterado sobre
        # un set, mientras el link apuntaba al EP de menor id (min()). Con
        # el mismo ejercicio en dos prácticas, la fila podía mostrar una
        # práctica distinta de la que la barra/link realmente abre.
        practica2 = Practica.objects.create(titulo='Z-otra-practica')
        pc2 = PracticaComision.objects.create(
            practica=practica2, comision=self.com, orden=2,
        )
        ep2 = EjercicioPractica.objects.create(
            practica=practica2, ejercicio=self.ep.ejercicio, orden=1,
        )
        _intento(self.est, ep2, True, pc=pc2)

        filas = _distribucion_intentos([self.com.id], [self.est.id])
        fila = next(f for f in filas if f['ep_id'] in (self.ep.id, ep2.id))
        ep_representante_id = min(self.ep.id, ep2.id)
        if ep_representante_id == self.ep.id:
            pc_esperado, practica_esperada = self.pc, self.pc.practica
        else:
            pc_esperado, practica_esperada = pc2, pc2.practica
        self.assertEqual(fila['ep_id'], ep_representante_id)
        self.assertEqual(fila['practica_titulo'], practica_esperada.titulo)
        self.assertEqual(fila['url'], f'/practica/{pc_esperado.id}/ejercicio/{ep_representante_id}/')


class DashboardHtmlLlevaUrlTests(TestCase):
    """El JSON servido al HTML del dashboard (lo que Chart.js realmente lee)
    tiene que traer la url, igual que ya se probó a nivel de dict en
    DashboardGraficosLlevanUrlTests. La suite de investigación ya cubría sus
    tres bloques (``test_la_url_llega_al_html_servido``); al dashboard le
    faltaban sus dos bloques."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('GRAF-DASH-HTML', n_estudiantes=1)
        self.est = self.ests[0]
        # 3 intentos: cfg.umbral_min_intentos por defecto es 3, así que
        # ejercicios_dificiles necesita esa cantidad para no venir vacío.
        _intento(self.est, self.ep, False, pc=self.pc)
        _intento(self.est, self.ep, False, pc=self.pc)
        _intento(self.est, self.ep, True, pc=self.pc)
        self.admin = _u('admin-graf-dash-html', is_staff=True, consentimiento_pedagogico=True)
        self.client.force_login(self.admin)

    def test_la_url_llega_al_html_servido(self):
        resp = self.client.get(reverse('analiticas:dashboard'))
        cuerpo = resp.content.decode('utf-8')
        esperada = f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/'
        for data_id in ('data-dificiles', 'data-distribucion'):
            bloque = re.search(rf'<script id="{data_id}"[^>]*>(.*?)</script>', cuerpo, re.DOTALL)
            self.assertIsNotNone(bloque, f'no se encontró el bloque {data_id}')
            self.assertIn(esperada, bloque.group(1), f'falla en {data_id}')


class ChartLinksPartialTests(TestCase):
    """El partial tiene que llegar a las dos páginas con gráficos por
    ejercicio, y a ninguna otra."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('PARTIAL', n_estudiantes=1)
        _intento(self.ests[0], self.ep, True, pc=self.pc)
        self.admin = _u('admin-partial', is_staff=True, consentimiento_pedagogico=True)
        self.client.force_login(self.admin)

    # Ojo: las dos páginas también LLAMAN a `enlazarEjerciciosDelEje(chart,
    # data)` en su propio <script> de armado de gráficos, esa llamada no
    # depende del partial. Si buscáramos solo el nombre de la función,
    # el test pasaría igual aunque el {% include %} desapareciera. Hay que
    # buscar la firma de la DEFINICIÓN, que vive únicamente en el partial.
    DEFINICION = 'function enlazarEjerciciosDelEje(chart, filas)'

    def test_dashboard_e_investigacion_cargan_el_helper(self):
        for nombre in ('analiticas:dashboard', 'analiticas:investigacion'):
            resp = self.client.get(reverse(nombre))
            self.assertContains(resp, self.DEFINICION, msg_prefix=nombre)

    def test_encuesta_no_lo_carga(self):
        # No tiene gráficos por ejercicio; cargarlo sería peso muerto.
        resp = self.client.get(reverse('analiticas:encuesta_resumen'))
        self.assertNotContains(resp, self.DEFINICION)
