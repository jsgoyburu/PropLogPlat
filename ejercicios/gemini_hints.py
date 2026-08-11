"""Generación opcional de pistas pedagógicas con Gemini (+ fallback Groq).

Este módulo NO reemplaza la devolución docente: produce una pista breve
orientada al proceso (sin dar la respuesta final), para sostener la práctica
cuando un intento no queda verificado.

Si Gemini devuelve 429 (cuota agotada) y GROQ_API_KEY está configurada,
se reintenta con Groq (llama-3.1-8b-instant, API compatible con OpenAI).
"""

from __future__ import annotations

import json
import logging
import os
from urllib import error, request

logger = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-lite:generateContent"
)
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_UA = "groq-python/0.9.0"
# Modelos en orden de preferencia para cada tarea.
# Se itera al siguiente solo si el anterior devuelve 429 (rate limit agotado).
_GROQ_MODELS_PISTAS = [
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.1-8b-instant",
]
_GROQ_MODELS_REVISION = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]


def _formatear_tabla(tabla: list[dict], max_filas: int = 8) -> str:
    if not tabla:
        return "  (vacía)"
    cols = list(tabla[0].keys())
    encabezado = " | ".join(cols)
    filas = []
    for fila in tabla[:max_filas]:
        filas.append(" | ".join("V" if fila.get(c) else "F" for c in cols))
    resultado = encabezado + "\n" + "\n".join(filas)
    if len(tabla) > max_filas:
        resultado += f"\n  … ({len(tabla) - max_filas} filas más)"
    return resultado


def _formatear_argumento(enunciados: list[dict]) -> str:
    lineas = []
    for e in enunciados:
        tipo = e.get("tipo", "?")
        formula = e.get("formula", "?")
        lineas.append(f"  {tipo.capitalize()}: {formula}")
    return "\n".join(lineas) if lineas else "  (vacío)"


def _prompt_formalizacion(
    enunciado: str,
    diccionario: dict | None,
    respuesta_estudiante: str,
    solucion_esperada: str | None,
    error_parse: str | None,
    resultado_motor: dict | None,
) -> str:
    dic_txt = (
        "\n".join(f"  {k} = \"{v}\"" for k, v in diccionario.items())
        if diccionario else "  (no proporcionado)"
    )
    motor_txt = []
    if error_parse:
        motor_txt.append(f"error de sintaxis: {error_parse}")
    if resultado_motor and resultado_motor.get("error_diccionario"):
        motor_txt.append(f"error de diccionario detectado por el sistema: {resultado_motor['error_diccionario']}")
    if not motor_txt:
        motor_txt.append("la tabla de verdad de la fórmula no equivale a la solución")
    motor_str = "; ".join(motor_txt)

    return (
        "Sos un/a tutor/a de lógica proposicional (CBC-UBA, nivel introductorio).\n"
        "Un/a estudiante intentó formalizar un enunciado y el motor lo marcó incorrecto.\n\n"
        f"Enunciado a formalizar: {enunciado}\n"
        f"Diccionario construido:\n{dic_txt}\n"
        f"Fórmula enviada: {respuesta_estudiante}\n"
        f"Lo que el motor detectó: {motor_str}.\n"
        f"Solución esperada (NO la reveles): {solucion_esperada or 'no disponible'}\n\n"
        "Analizá el intento completo, identificá dónde está el error más importante "
        "y escribí UNA sola pista orientadora (máx. 50 palabras). "
        "No des la fórmula ni el diccionario correctos. "
        "Evitá el efecto Topaze: guiá el razonamiento, no des la respuesta. "
        "Respondé SOLO con la pista, sin saludos, sin preámbulo, sin 'Pista:' al inicio.\n"
    )


def _columnas_con_errores(tabla_estudiante: list, resultado_motor: dict) -> list[str]:
    """Devuelve las columnas donde la tabla del estudiante difiere de la solución.

    Ordena ambas tablas con el mismo criterio que usa el motor (variables
    alfabéticas, True antes de False) para que la comparación sea independiente
    del orden de filas elegido por el/la estudiante.
    """
    tabla_correcta = resultado_motor.get("tabla_con_subcolumnas") or []
    if not tabla_estudiante or not tabla_correcta:
        return []

    variables_tabla = resultado_motor.get("variables_tabla") or []
    if variables_tabla:
        sort_fn = lambda row: tuple(not row.get(v, True) for v in variables_tabla)
        tabla_est_ord = sorted(tabla_estudiante, key=sort_fn)
    else:
        tabla_est_ord = list(tabla_estudiante)

    cols = list(tabla_estudiante[0].keys())
    errores = []
    for col in cols:
        for fila_est, fila_ok in zip(tabla_est_ord, tabla_correcta):
            if col in fila_ok and fila_est.get(col) != fila_ok.get(col):
                errores.append(col)
                break
    return errores


def _prompt_tabla_verdad(
    enunciado: str,
    diccionario: dict | None,
    enunciados_estudiante: list | None,
    solucion_esperada: str | None,
    juicio_valido: bool | None,
    tabla_estudiante: list | None,
    resultado_motor: dict | None,
) -> str:
    dic_txt = (
        "\n".join(f"  {k} = \"{v}\"" for k, v in diccionario.items())
        if diccionario else "  (no proporcionado)"
    )
    arg_txt = _formatear_argumento(enunciados_estudiante or [])
    juicio_txt = (
        "Válido" if juicio_valido is True
        else "No válido" if juicio_valido is False
        else "no indicado"
    )

    # Determinar qué falló y construir contexto específico para el prompt
    contexto_error = ""
    if resultado_motor:
        errores_parse = resultado_motor.get("errores_parse") or []
        if any(errores_parse):
            contexto_error = "Hay errores de sintaxis en alguna fórmula del argumento."

        elif not resultado_motor.get("formulas_ok"):
            contexto_error = (
                "Las fórmulas del argumento no coinciden con la solución: "
                "el/la estudiante identificó mal las premisas o la conclusión, "
                "o formalizó alguna incorrectamente."
            )

        elif resultado_motor.get("tabla_ok") is False:
            tabla_correcta = resultado_motor.get("tabla_con_subcolumnas") or []
            filas_est = len(tabla_estudiante or [])
            filas_ok = len(tabla_correcta)
            if filas_est != filas_ok:
                # Con distinta cantidad de filas la comparación posicional sería
                # engañosa: solo informamos el desajuste y no buscamos errores de columna.
                direccion = "faltan" if filas_est < filas_ok else "sobran"
                contexto_error = (
                    f"Las fórmulas son correctas pero la tabla tiene {filas_est} fila(s) "
                    f"cuando debería tener {filas_ok} ({direccion} {abs(filas_ok - filas_est)}). "
                    f"Orientá sobre cuántas filas debe tener una tabla de verdad completa "
                    f"en función de la cantidad de variables proposicionales distintas."
                )
            else:
                cols_error = _columnas_con_errores(tabla_estudiante or [], resultado_motor)
                if cols_error:
                    contexto_error = (
                        f"Las fórmulas son correctas y la tabla tiene el número correcto de filas, "
                        f"pero hay errores de evaluación en la(s) columna(s): {', '.join(cols_error)}. "
                        f"Enfocate en la regla lógica del conectivo principal de esa(s) fórmula(s), "
                        f"no analices la tabla entera."
                    )
                else:
                    contexto_error = "Las fórmulas son correctas pero hay celdas incorrectas en la tabla."

        elif resultado_motor.get("enunciados_ok") is False:
            contexto_error = (
                "Las fórmulas y la tabla son correctas pero los valores de las "
                "columnas de premisas o conclusión no coinciden con la solución."
            )

        elif resultado_motor.get("juicio_estudiante_valido") != resultado_motor.get("es_valido"):
            es_valido = resultado_motor.get("es_valido")
            contexto_error = (
                "Las fórmulas y la tabla son correctas pero el juicio de validez es incorrecto. "
                f"El argumento {'ES' if es_valido else 'NO ES'} válido según la tabla. "
                "Orientá sobre la definición de validez (¿existe alguna interpretación "
                "donde todas las premisas son V y la conclusión es F?)."
            )

    if not contexto_error:
        contexto_error = "El argumento no es correcto."

    return (
        "Sos un/a tutor/a de lógica proposicional (CBC-UBA, nivel introductorio).\n"
        "Un/a estudiante resolvió un ejercicio de argumento lógico y el motor lo marcó incorrecto.\n\n"
        f"Enunciado del argumento: {enunciado}\n"
        f"Diccionario construido:\n{dic_txt}\n"
        f"Argumento construido:\n{arg_txt}\n"
        f"Juicio del/la estudiante: {juicio_txt}\n"
        f"Diagnóstico del motor: {contexto_error}\n"
        f"Solución esperada (NO la reveles): {solucion_esperada or 'no disponible'}\n\n"
        "Escribí UNA sola pista orientadora (máx. 50 palabras) basada en el diagnóstico. "
        "No des el argumento ni los valores correctos de la tabla. "
        "Evitá el efecto Topaze: guiá el razonamiento, no des la respuesta. "
        "Respondé SOLO con la pista, sin saludos, sin preámbulo, sin 'Pista:' al inicio.\n"
    )


def _prompt_determinacion_verdad(
    enunciado: str,
    diccionario: dict | None,
    respuesta_estudiante: str,
    solucion_esperada: str | None,
    error_parse: str | None,
    resultado_motor: dict | None,
) -> str:
    dic_txt = (
        "\n".join(f"  {k} = \"{v}\"" for k, v in diccionario.items())
        if diccionario else "  (no proporcionado)"
    )
    motor_txt = []
    if error_parse:
        motor_txt.append(f"error de sintaxis: {error_parse}")
    if resultado_motor:
        if resultado_motor.get("consistente") is False:
            motor_txt.append(
                "el valor de verdad asignado a la fórmula no coincide "
                "con el que resulta de evaluarla con el propio diccionario"
            )
        elif resultado_motor.get("coincide_solucion") is False:
            motor_txt.append(
                "la fórmula es internamente consistente pero el resultado no coincide con la solución"
            )
    if not motor_txt:
        motor_txt.append("el resultado no coincide con la solución")
    motor_str = "; ".join(motor_txt)

    return (
        "Sos un/a tutor/a de lógica proposicional (CBC-UBA, nivel introductorio).\n"
        "Un/a estudiante resolvió un ejercicio de determinación de valor de verdad "
        "y el motor lo marcó incorrecto.\n\n"
        f"Enunciado a analizar: {enunciado}\n"
        f"Diccionario construido:\n{dic_txt}\n"
        f"Fórmula enviada: {respuesta_estudiante}\n"
        f"Lo que el motor detectó: {motor_str}.\n"
        f"Solución esperada (NO la reveles): {solucion_esperada or 'no disponible'}\n\n"
        "Analizá el intento completo, identificá dónde está el error más importante "
        "y escribí UNA sola pista orientadora (máx. 50 palabras). "
        "No des la fórmula ni el diccionario correctos. "
        "Evitá el efecto Topaze: guiá el razonamiento, no des la respuesta. "
        "Respondé SOLO con la pista, sin saludos, sin preámbulo, sin 'Pista:' al inicio.\n"
    )


def _groq_request(prompt: str, models: list[str], max_tokens: int, temperature: float) -> str | None:
    """Llama a Groq probando los modelos en orden; avanza al siguiente solo en 429."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    for model in models:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = request.Request(
            _GROQ_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": _GROQ_UA,
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"].strip()
            return text if text else None
        except error.HTTPError as exc:
            body = ''
            try:
                body = exc.read().decode('utf-8')[:300]
            except Exception:
                pass
            if exc.code == 429:
                logger.warning("Groq model %s rate limited, probando siguiente — %s", model, body)
                continue
            logger.warning("Groq unavailable (%s): %s — %s", model, exc, body)
            return None
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            logger.warning("Groq unavailable (%s): %s", model, exc)
            return None

    logger.warning("Todos los modelos Groq agotaron el rate limit")
    return None


def _llamar_groq(prompt: str) -> str | None:
    """Fallback a Groq cuando Gemini alcanza su límite de cuota."""
    text = _groq_request(prompt, _GROQ_MODELS_PISTAS, max_tokens=120, temperature=0.2)
    return text[:400] if text else None


def revisar_diccionario_groq(enunciado: str, diccionario: dict) -> str | None:
    """Revisa con Groq si el diccionario estudiantil es una simbolización razonable del enunciado.

    Retorna ``'pasa'``, ``'revisar'``, o ``None`` si Groq no está disponible.
    Solo se llama en intentos correctos con diccionario no vacío.
    """
    dic_lines = "\n".join(f"  {k}: {v}" for k, v in diccionario.items())
    prompt = (
        "Evaluás diccionarios de simbolización lógica proposicional. "
        "Respondé únicamente 'Pasa' o 'Revisar'.\n\n"
        "Respondé 'Pasa' si cada entrada del diccionario corresponde a un hecho atómico "
        "reconocible en el enunciado (puede estar abreviada o incompleta). "
        "Ignorá errores de tipeo o autocorrector que no cambian el sentido "
        "(ej: 'Juegan es abogado' por 'Juan es abogado').\n"
        "Respondé 'Revisar' solo si alguna entrada: "
        "(a) tiene sujeto plural o ambiguo que esconde un enunciado compuesto, "
        "(b) es un fragmento nominal sin predicado, "
        "o (c) no guarda relación con el enunciado.\n\n"
        "---\n"
        "Enunciado: \"Juan es abogado y fanático de Miranda, o María es abogada y fanática de Miranda.\"\n"
        "Diccionario:\n"
        "  A: María es fanática de Miranda\n"
        "  F: Juan es fanático de Miranda\n"
        "  J: Juan es abogado\n"
        "  M: María es abogada\n"
        "Respuesta: Pasa\n\n"
        "---\n"
        "Enunciado: \"Siempre que la presión tectónica supera el límite de ruptura, se genera un sismo.\"\n"
        "Diccionario:\n"
        "  P: presión tectónica supera el límite\n"
        "  Q: se genera un sismo\n"
        "Respuesta: Pasa\n\n"
        "---\n"
        "Enunciado: \"Si Miranda canta, los fanáticos van al recital.\"\n"
        "Diccionario:\n"
        "  P: Miranda canta\n"
        "  Q: son fanáticos de Miranda\n"
        "Respuesta: Revisar\n\n"
        "---\n"
        "Enunciado: \"Si Juan estudia, aprueba el examen.\"\n"
        "Diccionario:\n"
        "  P: Juan estudia\n"
        "  Q: Juan aprueba y festeja\n"
        "Respuesta: Revisar\n\n"
        "---\n"
        f"Enunciado: \"{enunciado}\"\n"
        f"Diccionario:\n{dic_lines}\n"
        "Respuesta:"
    )

    text = _groq_request(prompt, _GROQ_MODELS_REVISION, max_tokens=10, temperature=0.1)
    if not text:
        return None
    text = text.lower()
    if "revisar" in text:
        return "revisar"
    if "pasa" in text:
        return "pasa"
    return None


_PROMPT_CIRUGIA = """\
Evaluás respuestas a un acertijo de pensamiento lateral sobre sesgo de género en la ciencia \
(CBC-UBA). Respondé únicamente "Correcto" o "Incorrecto".

Enunciado: Un chico y su padre sufren un accidente de tránsito. El padre muere en el lugar. \
El chico llega al hospital en estado crítico. El cirujano/a llega, lo mira y dice: \
"No puedo operarlo, es mi hijo." ¿Cómo es esto posible?

La respuesta es CORRECTA si identifica que la persona que dice "es mi hijo" es la MADRE del chico \
(o un segundo progenitor en una familia con dos padres del mismo sexo). \
Puede estar formulado de cualquier manera: "es la madre", "la mamá es la médica", \
términos no binarios como "xadre", etc.

La respuesta es INCORRECTA si:
- Identifica al cirujano como el abuelo, tío, padrastro u otro pariente que no es progenitor directo.
- Hace al padre del accidente el mismo que el médico (sin explicar cómo murió y opera al mismo tiempo).
- Dice que es imposible, no tiene sentido, o cambia quién sufrió el accidente sin resolver la contradicción.
- Solo dice "no sé" o está vacía.

Ejemplos:
Respuesta: "Es la madre" → Correcto
Respuesta: "La madre es la doctora." → Correcto
Respuesta: "Su mamá es la doctora" → Correcto
Respuesta: "Podrían ser la madre" → Correcto
Respuesta: "porque la persona medicx que debe operarlo es xadre del niño" → Correcto
Respuesta: "Porque la persona que tendría que operarlo sería la madre/padre del mismo. \
Por ende y por ley no se puede operar a un círculo familiar de primer linaje." → Correcto
Respuesta: "Es el padre del padre" → Incorrecto
Respuesta: "El padre es el doctor." → Incorrecto
Respuesta: "Si los dos sufrieron un accidente, el padre también debería estar internado" → Incorrecto
Respuesta: "WTF, no tiene sentido." → Incorrecto
Respuesta: "Porque no dice que es el padre y su hijo, es un padre y un hijo." → Incorrecto

Respuesta del/la estudiante: "{respuesta}"
Respuesta:"""


def evaluar_cirugia_groq(respuesta_texto: str) -> bool | None:
    """Evalúa con Groq si la respuesta al acertijo de cirugía es correcta.

    Returns True (correcto), False (incorrecto), None (no se pudo evaluar — Groq no disponible).
    """
    respuesta_texto = (respuesta_texto or '').strip()
    if not respuesta_texto or respuesta_texto.lower() in ('no sé', 'no se', 'no sé.', 'no se.'):
        return False

    prompt = _PROMPT_CIRUGIA.format(respuesta=respuesta_texto[:500])
    text = _groq_request(prompt, _GROQ_MODELS_REVISION, max_tokens=10, temperature=0.1)
    if not text:
        return None
    text_lower = text.lower().strip()
    first_word = text_lower.split()[0] if text_lower else ''
    # Priorizar primera palabra para evitar colisiones por subcadenas
    if first_word in ('incorrecto', 'incorrecta'):
        return False
    if first_word in ('correcto', 'correcta'):
        return True
    # Fallback: buscar subcadena solo si la primera palabra no fue concluyente
    if 'incorrecto' in text_lower or 'incorrecta' in text_lower:
        return False
    if 'correcto' in text_lower or 'correcta' in text_lower:
        return True
    return None


def generar_pista_gemini(
    *,
    tipo_ejercicio: str,
    enunciado: str,
    respuesta_estudiante: str,
    solucion_esperada: str | None = None,
    error_parse: str | None = None,
    diccionario: dict | None = None,
    enunciados_estudiante: list | None = None,
    tabla_estudiante: list | None = None,
    juicio_valido: bool | None = None,
    resultado_motor: dict | None = None,
) -> str | None:
    """Devuelve una pista semántica breve si hay API key configurada.

    Retorna ``None`` en cualquier error de red/configuración para no bloquear
    el flujo principal de intentos.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    if tipo_ejercicio == "tabla_verdad":
        prompt = _prompt_tabla_verdad(
            enunciado=enunciado,
            diccionario=diccionario,
            enunciados_estudiante=enunciados_estudiante,
            solucion_esperada=solucion_esperada,
            juicio_valido=juicio_valido,
            tabla_estudiante=tabla_estudiante,
            resultado_motor=resultado_motor,
        )
    elif tipo_ejercicio == "determinacion_verdad":
        prompt = _prompt_determinacion_verdad(
            enunciado=enunciado,
            diccionario=diccionario,
            respuesta_estudiante=respuesta_estudiante,
            solucion_esperada=solucion_esperada,
            error_parse=error_parse,
            resultado_motor=resultado_motor,
        )
    else:
        prompt = _prompt_formalizacion(
            enunciado=enunciado,
            diccionario=diccionario,
            respuesta_estudiante=respuesta_estudiante,
            solucion_esperada=solucion_esperada,
            error_parse=error_parse,
            resultado_motor=resultado_motor,
        )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 120},
    }
    req = request.Request(
        f"{_GEMINI_URL}?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        logger.warning("Gemini API HTTP Error %s: %s", exc.code, error_body)
        if exc.code == 429:
            logger.info("Gemini quota exceeded, trying Groq fallback")
            return _llamar_groq(prompt)
        return None
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Gemini hint unavailable: %s", exc)
        return None

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return None

    return text[:400] if text else None
