# Paquetes portables de prácticas y ejercicios

PropLogPlat comparte material mediante un ZIP que contiene un único archivo
`package.json` UTF-8. El formato público actual es
`ipc-logica-package`, versión `1`.

Cada paquete declara `CC-BY-SA-4.0`: al redistribuirlo o adaptarlo hay que
reconocer su procedencia, indicar los cambios y conservar esa licencia.

## Qué incluye

- castellano original y traducciones opcionales al inglés, francés y alemán;
- título y descripción de la práctica;
- consignas, tipos y orden de ejercicios;
- fórmulas, diccionarios y valores de verdad usados para la verificación formal.

## Qué nunca incluye

- nombres, cuentas o correos;
- comisiones o inscripciones;
- intentos, progreso, comentarios o aprobaciones;
- analíticas o respuestas de investigación;
- claves de servicios externos.

Al instalar, todo se crea como copia privada del docente que sube el archivo.
Nada se publica automáticamente en el banco común y nada se asigna a una
comisión hasta que una persona lo revise.

La importación valida el ZIP, limita su tamaño, rechaza archivos adicionales,
convierte el contenido enriquecido a texto seguro y vuelve a validar cada
fórmula con el mismo editor docente. Si una parte falla, la transacción completa
se revierte.

El contrato formal está en `schemas/ipc-logica-package-v1.schema.json`. Para una
versión incompatible se debe crear otro schema y mantener el lector v1; nunca
se debe reinterpretar silenciosamente un paquete existente.
