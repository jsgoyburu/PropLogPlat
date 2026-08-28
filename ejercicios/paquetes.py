"""Paquetes portables de prácticas y ejercicios.

El formato v1 es un ZIP con un único ``package.json``. Transporta solamente
contenido pedagógico y nunca incluye personas, comisiones, intentos o métricas.
"""

from __future__ import annotations

import io
import json
import zipfile
from html import unescape

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from ejercicios.models import Ejercicio, EjercicioPractica, Practica


FORMATO = 'ipc-logica-package'
VERSION = 1
NOMBRE_JSON = 'package.json'
MAX_ARCHIVO = 5 * 1024 * 1024
MAX_JSON = 5 * 1024 * 1024
TIPOS_EJERCICIO = {valor for valor, _etiqueta in Ejercicio.TIPO_CHOICES}
IDIOMAS_CONTENIDO = ('es', 'en', 'fr', 'de', 'zh-hans')


class PaqueteInvalido(ValueError):
    """El archivo no cumple el contrato público del paquete."""


def _texto_plano(valor):
    """Normaliza HTML autorado a texto portable y seguro."""
    return unescape(strip_tags(valor or '')).strip()


def _ejercicio_dict(ejercicio):
    return {
        'enunciado': {
            'es': _texto_plano(ejercicio.enunciado),
            'en': _texto_plano(ejercicio.enunciado_en),
            'fr': _texto_plano(ejercicio.enunciado_fr),
            'de': _texto_plano(ejercicio.enunciado_de),
            'zh-hans': _texto_plano(ejercicio.enunciado_zh_hans),
        },
        'tipo': ejercicio.tipo,
        'formula_solucion': ejercicio.formula_solucion,
        'diccionario_solucion': ejercicio.diccionario_solucion or {},
        'valores_verdad_solucion': ejercicio.valores_verdad_solucion,
    }


def paquete_ejercicio(ejercicio):
    """Serializa un ejercicio sin IDs internos ni datos de autoría personal."""
    return {
        'format': FORMATO,
        'version': VERSION,
        'kind': 'exercise',
        'license': 'CC-BY-SA-4.0',
        'source_application': 'PropLogPlat',
        'exported_at': timezone.now().isoformat(),
        'content': _ejercicio_dict(ejercicio),
    }


def paquete_practica(practica):
    """Serializa una práctica y sus ejercicios en su orden pedagógico."""
    ejercicios = []
    for ep in practica.ejercicio_practicas.select_related('ejercicio').order_by('orden'):
        item = _ejercicio_dict(ep.ejercicio)
        item['order'] = ep.orden
        ejercicios.append(item)

    return {
        'format': FORMATO,
        'version': VERSION,
        'kind': 'practice',
        'license': 'CC-BY-SA-4.0',
        'source_application': 'PropLogPlat',
        'exported_at': timezone.now().isoformat(),
        'content': {
            'title': {
                'es': _texto_plano(practica.titulo),
                'en': _texto_plano(practica.titulo_en),
                'fr': _texto_plano(practica.titulo_fr),
                'de': _texto_plano(practica.titulo_de),
                'zh-hans': _texto_plano(practica.titulo_zh_hans),
            },
            'description': {
                'es': _texto_plano(practica.descripcion),
                'en': _texto_plano(practica.descripcion_en),
                'fr': _texto_plano(practica.descripcion_fr),
                'de': _texto_plano(practica.descripcion_de),
                'zh-hans': _texto_plano(practica.descripcion_zh_hans),
            },
            'exercises': ejercicios,
        },
    }


def comprimir_paquete(payload):
    """Devuelve bytes ZIP reproducibles con JSON UTF-8 legible."""
    json_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode('utf-8')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archivo:
        info = zipfile.ZipInfo(NOMBRE_JSON)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        archivo.writestr(info, json_bytes)
    return buffer.getvalue()


def leer_paquete(archivo):
    """Lee y valida la envoltura ZIP sin extraer archivos al disco."""
    if getattr(archivo, 'size', 0) > MAX_ARCHIVO:
        raise PaqueteInvalido('El paquete supera el máximo de 5 MB.')

    try:
        with zipfile.ZipFile(archivo) as comprimido:
            nombres = comprimido.namelist()
            if nombres != [NOMBRE_JSON]:
                raise PaqueteInvalido(
                    'El ZIP debe contener únicamente un archivo package.json.'
                )
            info = comprimido.getinfo(NOMBRE_JSON)
            if info.file_size > MAX_JSON:
                raise PaqueteInvalido('El JSON descomprimido supera el máximo de 5 MB.')
            raw = comprimido.read(info)
    except (zipfile.BadZipFile, RuntimeError, OSError) as error:
        raise PaqueteInvalido('El archivo no es un ZIP válido.') from error

    try:
        payload = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaqueteInvalido('package.json no contiene JSON UTF-8 válido.') from error

    _validar_envoltura(payload)
    return payload


def _validar_envoltura(payload):
    if not isinstance(payload, dict):
        raise PaqueteInvalido('La raíz del paquete debe ser un objeto JSON.')
    if payload.get('format') != FORMATO or payload.get('version') != VERSION:
        raise PaqueteInvalido('Formato o versión de paquete no compatible.')
    if payload.get('license') != 'CC-BY-SA-4.0':
        raise PaqueteInvalido('El paquete debe declarar la licencia CC-BY-SA-4.0.')
    if payload.get('source_application') != 'PropLogPlat':
        raise PaqueteInvalido('El paquete no identifica una aplicación de origen compatible.')
    if payload.get('kind') not in {'practice', 'exercise'}:
        raise PaqueteInvalido('El tipo de paquete debe ser practice o exercise.')
    if not isinstance(payload.get('content'), dict):
        raise PaqueteInvalido('El paquete no contiene un objeto content válido.')


def _mapa_idiomas(valor, campo, *, obligatorio_es=True, max_length=10000):
    if not isinstance(valor, dict):
        raise PaqueteInvalido(f'{campo} debe contener traducciones por idioma.')
    limpio = {}
    for idioma in IDIOMAS_CONTENIDO:
        texto = valor.get(idioma, '')
        if texto is None:
            texto = ''
        if not isinstance(texto, str):
            raise PaqueteInvalido(f'{campo}.{idioma} debe ser texto.')
        texto = _texto_plano(texto)
        if len(texto) > max_length:
            raise PaqueteInvalido(f'{campo}.{idioma} es demasiado largo.')
        limpio[idioma] = texto
    if obligatorio_es and not limpio['es']:
        raise PaqueteInvalido(f'{campo}.es es obligatorio porque conserva el original.')
    return limpio


def _datos_ejercicio(data):
    if not isinstance(data, dict):
        raise PaqueteInvalido('Cada ejercicio debe ser un objeto JSON.')
    enunciado = _mapa_idiomas(data.get('enunciado'), 'enunciado')
    tipo = data.get('tipo')
    if tipo not in TIPOS_EJERCICIO:
        raise PaqueteInvalido('El ejercicio tiene un tipo no compatible.')
    formula = data.get('formula_solucion')
    if not isinstance(formula, str) or not formula.strip() or len(formula) > 500:
        raise PaqueteInvalido('La fórmula solución es obligatoria y admite hasta 500 caracteres.')
    diccionario = data.get('diccionario_solucion', {})
    if not isinstance(diccionario, dict):
        raise PaqueteInvalido('diccionario_solucion debe ser un objeto JSON.')
    valores = data.get('valores_verdad_solucion')
    if valores is not None and not isinstance(valores, dict):
        raise PaqueteInvalido('valores_verdad_solucion debe ser un objeto JSON o null.')
    return {
        'enunciado': enunciado,
        'tipo': tipo,
        'formula_solucion': formula.strip(),
        'diccionario_solucion': diccionario,
        'valores_verdad_solucion': valores,
    }


def _crear_ejercicio(data, usuario):
    datos = _datos_ejercicio(data)
    # Reusar la validación formal del editor docente; evita instalar fórmulas
    # que el sitio no podría verificar después.
    from docentes.forms import EjercicioForm

    form = EjercicioForm(data={
        'enunciado': datos['enunciado']['es'],
        'formula_solucion': datos['formula_solucion'],
        'tipo': datos['tipo'],
        'es_publico': False,
    })
    if not form.is_valid():
        raise PaqueteInvalido(
            'Un ejercicio no supera la validación formal: '
            + '; '.join(
                mensaje
                for errores in form.errors.values()
                for mensaje in errores
            )
        )

    ejercicio = form.save(commit=False)
    ejercicio.creado_por = usuario
    ejercicio.es_publico = False
    ejercicio.enunciado_en = datos['enunciado']['en']
    ejercicio.enunciado_fr = datos['enunciado']['fr']
    ejercicio.enunciado_de = datos['enunciado']['de']
    ejercicio.enunciado_zh_hans = datos['enunciado']['zh-hans']
    ejercicio.diccionario_solucion = datos['diccionario_solucion']
    ejercicio.valores_verdad_solucion = datos['valores_verdad_solucion']
    try:
        ejercicio.full_clean(exclude=['creado_por'])
    except ValidationError as error:
        raise PaqueteInvalido(f'El ejercicio contiene datos inválidos: {error}') from error
    ejercicio.save()
    return ejercicio


@transaction.atomic
def instalar_paquete(payload, usuario):
    """Instala contenido como copia privada y devuelve ``(kind, objeto)``."""
    _validar_envoltura(payload)
    content = payload['content']

    if payload['kind'] == 'exercise':
        return 'exercise', _crear_ejercicio(content, usuario)

    titulo = _mapa_idiomas(
        content.get('title'), 'content.title', max_length=200,
    )
    descripcion = _mapa_idiomas(
        content.get('description', {'es': ''}),
        'content.description',
        obligatorio_es=False,
    )
    ejercicios = content.get('exercises')
    if not isinstance(ejercicios, list) or not ejercicios:
        raise PaqueteInvalido('Una práctica debe contener al menos un ejercicio.')
    if len(ejercicios) > 500:
        raise PaqueteInvalido('Una práctica no puede contener más de 500 ejercicios.')

    practica = Practica.objects.create(
        titulo=titulo['es'],
        titulo_en=titulo['en'],
        titulo_fr=titulo['fr'],
        titulo_de=titulo['de'],
        titulo_zh_hans=titulo['zh-hans'],
        descripcion=descripcion['es'],
        descripcion_en=descripcion['en'],
        descripcion_fr=descripcion['fr'],
        descripcion_de=descripcion['de'],
        descripcion_zh_hans=descripcion['zh-hans'],
        es_publica=False,
        creada_por=usuario,
        practica_origen=None,
    )

    ordenes = []
    for posicion, data in enumerate(ejercicios, start=1):
        orden = data.get('order', posicion) if isinstance(data, dict) else posicion
        if not isinstance(orden, int) or orden < 1:
            raise PaqueteInvalido('El orden de los ejercicios debe ser un entero positivo.')
        ordenes.append(orden)
    if len(set(ordenes)) != len(ordenes):
        raise PaqueteInvalido('Los órdenes de los ejercicios no pueden repetirse.')

    for orden, data in sorted(zip(ordenes, ejercicios), key=lambda par: par[0]):
        ejercicio = _crear_ejercicio(data, usuario)
        EjercicioPractica.objects.create(
            practica=practica,
            ejercicio=ejercicio,
            orden=orden,
        )

    return 'practice', practica
