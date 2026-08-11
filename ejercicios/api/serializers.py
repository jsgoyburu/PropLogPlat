"""Serializers DRF para la API de intentos.

Solo el serializer de entrada (IntentoInputSerializer) es necesario
para el endpoint POST /api/intentos/. El cuerpo de la respuesta se
construye directamente en la view con el resultado del motor lógico
más los campos del intento guardado.
"""

from rest_framework import serializers

from ejercicios.models import EjercicioPractica


class IntentoInputSerializer(serializers.Serializer):
    """Datos de entrada para POST /api/intentos/.

    Para ejercicios de tipo ``formalizacion``: usar ``respuesta_raw``.
    Para ejercicios de tipo ``tabla_verdad``: usar ``enunciados`` y ``juicio_valido``.
    Para ejercicios de tipo ``determinacion_verdad``: usar ``respuesta_raw``,
    ``valores_verdad`` y ``valor_verdad_estudiante``.

    Attributes:
        ejercicio_practica_id (int): ID del :class:`~ejercicios.models.EjercicioPractica`
            que el estudiante está resolviendo.
        practica_comision_id (int): ID del :class:`~ejercicios.models.PracticaComision`
            desde el que el estudiante está resolviendo. Determina la comisión
            del intento, el modo de desbloqueo y la fila de ``Progreso``.
        respuesta_raw (str): fórmula enviada por el estudiante en ASCII
            normalizado (para ejercicios de formalización y determinación de verdad).
        enunciados (list): lista de dicts ``{"formula": str, "tipo": str}``
            para ejercicios de tabla de verdad (argumento lógico).
        juicio_valido (bool): si el estudiante marcó el argumento como válido
            (solo para ejercicios de tabla de verdad).
        valores_verdad (dict): mapa ``{letra: bool}`` con el valor de verdad
            asignado por el estudiante a cada variable (determinación de verdad).
        valor_verdad_estudiante (bool): valor de verdad que el estudiante
            declara para su fórmula (determinación de verdad).
    """

    ejercicio_practica_id = serializers.IntegerField(
        help_text='ID del EjercicioPractica que se está resolviendo.',
    )
    practica_comision_id = serializers.IntegerField(
        help_text='ID del PracticaComision desde el que se está resolviendo. '
                  'Determina la comisión del intento y su fila de progreso.',
    )
    respuesta_raw = serializers.CharField(
        max_length=2000,
        allow_blank=True,
        required=False,
        default='',
        trim_whitespace=True,
        help_text='Fórmula del estudiante en ASCII normalizado (para formalización).',
    )
    diccionario = serializers.DictField(
        child=serializers.CharField(max_length=200),
        required=False,
        default=dict,
        help_text='Mapa {letra: proposición} construido por el estudiante. Ej: {"A": "Llueve"}.',
    )
    enunciados = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
        help_text='Lista de {"formula": str, "tipo": "premisa"|"conclusion"} para tabla de verdad.',
    )
    juicio_valido = serializers.BooleanField(
        required=False,
        default=None,
        allow_null=True,
        help_text='True si el estudiante considera válido el argumento (tabla de verdad).',
    )
    tabla_estudiante = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=None,
        allow_null=True,
        help_text='Tabla de verdad completada por el estudiante: '
                  'lista de filas, cada una con claves = labels de columnas de fórmulas '
                  '(subcolumnas y P1/P2/.../C) y valores bool.',
    )
    valores_verdad = serializers.DictField(
        child=serializers.BooleanField(),
        required=False,
        default=None,
        allow_null=True,
        help_text='Mapa {letra: bool} con el valor de verdad asignado por el estudiante a cada variable. '
                  'Solo para ejercicios de determinación de verdad. Ej: {"A": true, "B": false}.',
    )
    valor_verdad_estudiante = serializers.BooleanField(
        required=False,
        default=None,
        allow_null=True,
        help_text='Valor de verdad que el estudiante declara para su fórmula (V=true / F=false). '
                  'Solo para ejercicios de determinación de verdad.',
    )

    def validate_ejercicio_practica_id(self, value: int) -> int:
        """Verifica que el EjercicioPractica existe.

        Args:
            value: ID a validar.

        Returns:
            El mismo ID si existe.

        Raises:
            serializers.ValidationError: si no existe ningún
                EjercicioPractica con ese ID.
        """
        if not EjercicioPractica.objects.filter(pk=value).exists():
            raise serializers.ValidationError(
                f'No existe un ejercicio en práctica con id={value}.'
            )
        return value


class PreviewVerificacionSerializer(serializers.Serializer):
    """Datos de entrada para POST /api/preview-verificacion/.

    Attributes:
        formula_solucion (str): fórmula solución del ejercicio en edición.
        respuesta_prueba (str): respuesta ingresada para probar la corrección.
    """

    formula_solucion = serializers.CharField(
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
        help_text='Fórmula solución a validar y usar como referencia.',
    )
    respuesta_prueba = serializers.CharField(
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
        help_text='Respuesta de prueba para validar equivalencia tabular.',
    )


class IntentoComentarioUpdateSerializer(serializers.Serializer):
    """Datos de entrada para actualizar comentario docente de un intento.

    Attributes:
        comentario_docente (str): comentario opcional asociado al intento.
    """

    comentario_docente = serializers.CharField(
        max_length=2000,
        allow_blank=True,
        trim_whitespace=False,
        required=True,
        help_text='Comentario docente para asociar al intento.',
    )


class PreviewArgumentoSerializer(serializers.Serializer):
    """Datos de entrada para POST /api/preview-argumento/.

    Permite al docente probar la corrección de un argumento en el sandbox
    antes de guardar el ejercicio. También es usado por el estudiante para
    obtener la estructura de columnas de la tabla de verdad (Paso 3).

    Attributes:
        enunciados_solucion (list): el argumento del docente (solución).
            Si se omite, se usa ``enunciados_prueba`` como solución de
            referencia (útil para que el estudiante genere la tabla).
        enunciados_prueba (list): el argumento de prueba a verificar.
        juicio_valido (bool): si la prueba marca el argumento como válido.
    """

    enunciados_solucion = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=None,
        allow_empty=True,
        help_text='Argumento de la solución: lista de {"formula": str, "tipo": str}. '
                  'Si se omite, se usa enunciados_prueba como referencia.',
    )
    enunciados_prueba = serializers.ListField(
        child=serializers.DictField(),
        help_text='Argumento de prueba: lista de {"formula": str, "tipo": str}.',
    )
    juicio_valido = serializers.BooleanField(
        allow_null=True,
        default=None,
        required=False,
        help_text='True si la prueba marca el argumento como válido.',
    )


class PreviewDeterminacionSerializer(serializers.Serializer):
    """Datos de entrada para POST /api/preview-determinacion/.

    Permite al docente ver dinámicamente el valor de verdad de su fórmula
    solución dado el diccionario con valores de verdad asignados.
    También permite verificar una respuesta de prueba antes de guardar.

    Attributes:
        formula (str): fórmula a evaluar.
        valores_verdad (dict): mapa ``{letra: bool}`` con los valores de verdad
            asignados a cada variable.
    """

    formula = serializers.CharField(
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
        help_text='Fórmula a evaluar.',
    )
    valores_verdad = serializers.DictField(
        child=serializers.BooleanField(),
        help_text='Mapa {letra: bool} con el valor de verdad de cada variable. Ej: {"A": true, "B": false}.',
    )
