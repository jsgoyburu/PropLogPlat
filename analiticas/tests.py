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

import uuid
from datetime import date, datetime
from types import SimpleNamespace

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
    _distribucion_intentos,
    _ejercicios_mas_dificiles,
    _errores_sistematicos,
    _estudiantes_en_riesgo,
    _evolucion_temporal,
    _silencio_temprano,
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
            [self.comision.id], [self.estudiante.id], min_intentos=1, cohorte_id=self.c1.id,
        )
        con_c2 = _ejercicios_mas_dificiles(
            [self.comision.id], [self.estudiante.id], min_intentos=1, cohorte_id=self.c2.id,
        )

        self.assertEqual(len(con_c1), 1)
        self.assertEqual(con_c1[0]['total'], 4)
        self.assertEqual(con_c2, [])

    def test_silencio_temprano_no_mezcla_cohortes_del_recursante(self):
        filas_c2 = _silencio_temprano([self.comision.id], [self.estudiante.id], cohorte_id=self.c2.id)

        self.assertEqual(len(filas_c2), 1)
        # Sin intentos en c2, el estudiante debe verse como "nunca intentó",
        # no arrastrar el último intento de c1.
        self.assertTrue(filas_c2[0]['nunca'])
        self.assertEqual(filas_c2[0]['total_intentos'], 0)

        filas_c1 = _silencio_temprano([self.comision.id], [self.estudiante.id], cohorte_id=self.c1.id)
        self.assertFalse(filas_c1[0]['nunca'])
        self.assertEqual(filas_c1[0]['total_intentos'], 4)

    def test_estudiantes_en_riesgo_no_mezcla_cohortes_del_recursante(self):
        en_riesgo_c1 = _estudiantes_en_riesgo(
            [self.comision.id], [self.estudiante.id], umbral_riesgo=4, cohorte_id=self.c1.id,
        )
        en_riesgo_c2 = _estudiantes_en_riesgo(
            [self.comision.id], [self.estudiante.id], umbral_riesgo=4, cohorte_id=self.c2.id,
        )

        self.assertEqual(len(en_riesgo_c1), 1)
        self.assertEqual(en_riesgo_c1[0]['racha'], 4)
        self.assertEqual(en_riesgo_c2, [])

    def test_sin_cohorte_id_preserva_el_comportamiento_agregado(self):
        """El dashboard agregado (varias comisiones, sin cohorte) no debe
        acotarse: cohorte_id=None (default) sigue viendo todo lo del
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
