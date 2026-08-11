"""Helpers para mapear facultades/carreras desde JSON al esquema interno."""

import json
from functools import lru_cache
from pathlib import Path

from accounts.models import CARRERA_CHOICES, FACULTAD_CHOICES


def _normalizar(texto):
    reemplazos = str.maketrans(
        'áéíóúüñÁÉÍÓÚÜÑ',
        'aeiouunAEIOUUN',
    )
    return (texto or '').translate(reemplazos).lower().strip()


@lru_cache(maxsize=1)
def get_facultades_carreras_por_clave():
    """Devuelve un mapa facultad->carreras usando claves de choices del sistema."""
    path = Path(__file__).resolve().parent.parent / 'facultades_carreras.json'
    if not path.exists():
        return {}

    with path.open(encoding='utf-8') as fh:
        payload = json.load(fh)

    facultad_por_nombre = {_normalizar(label): value for value, label in FACULTAD_CHOICES}
    carrera_por_nombre = {_normalizar(label): value for value, label in CARRERA_CHOICES}

    alias_carrera = {
        'licenciatura en administracion': 'administracion',
        'licenciatura en economia': 'economia',
        'licenciatura en sistemas de informacion de las organizaciones': 'sistemas_info_org',
        'licenciatura en ciencias biologicas': 'ciencias_biologicas',
        'licenciatura en ciencias de datos': 'ciencias_datos',
        'licenciatura en ciencias de la atmosfera': 'ciencias_atmosfera',
        'licenciatura en ciencias de la computacion': 'ciencias_computacion',
        'licenciatura en ciencias fisicas': 'ciencias_fisicas',
        'licenciatura en ciencias geologicas': 'ciencias_geologicas',
        'licenciatura en ciencias matematicas': 'ciencias_matematicas',
        'licenciatura en ciencias quimicas': 'ciencias_quimicas',
        'licenciatura en ciencia y tecnologia de alimentos': 'ciencia_tec_alimentos',
        'licenciatura en ciencias oceanograficas': 'oceanografia',
        'licenciatura en kinesiologia y fisiatria': 'kinesiologia',
        'licenciatura en nutricion': 'nutricion',
        'licenciatura en obstetricia': 'obstetricia',
        'licenciatura en produccion de bioimagenes': 'radiologia',
        'licenciatura en psicologia': 'psicologia',
        'veterinaria': 'ciencias_veterinarias',
        'ingenieria naval': 'ingenieria_naval',
        'ingenieria en alimentos': 'ingenieria_alimentos',
        'ingenieria en energia electrica': 'ingenieria_electricista',
        'licenciatura en analisis de sistemas': 'ingenieria_informatica',
        'bibliotecologia y ciencias de la informacion': 'bibliotecologia',
        'tecnicatura universitaria en gestion integral de bioterios': 'bioterios',
        'tecnicatura universitaria en cosmetologia facial y corporal': 'cosmetologia',
        'tecnicatura universitaria en hemoterapia e inmunohematologia': 'hemoterapia',
        'tecnicatura universitaria en instrumentacion quirurgica': 'instrumentacion_qx',
        'tecnicatura universitaria en podologia': 'podologia',
        'tecnicatura universitaria en practicas cardiologicas': 'practicas_cardiologicas',
        'terapia ocupacional': 'terapia_ocupacional',
    }

    resultado = {}
    for facultad in payload.get('facultades', []):
        nombre_facultad = facultad.get('nombre', '').replace('Facultad de ', '')
        clave_facultad = facultad_por_nombre.get(_normalizar(nombre_facultad))
        if not clave_facultad:
            continue

        carreras = []
        for bloque in (facultad.get('carreras') or {}).values():
            for nombre_carrera in bloque:
                normalizada = _normalizar(nombre_carrera)
                clave = carrera_por_nombre.get(normalizada) or alias_carrera.get(normalizada)
                if clave and clave not in carreras:
                    carreras.append(clave)

        if carreras:
            resultado[clave_facultad] = carreras

    return resultado


@lru_cache(maxsize=1)
def get_carreras_unificadas_por_clave():
    """Devuelve carreras únicas del JSON, sin separar por facultad."""
    mapa = get_facultades_carreras_por_clave()
    if not mapa:
        return [value for value, _ in CARRERA_CHOICES]

    resultado = []
    for carreras in mapa.values():
        for carrera in carreras:
            if carrera not in resultado:
                resultado.append(carrera)
    return resultado
