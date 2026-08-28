# Crear y mantener un fork propio

Un fork de PropLogPlat puede cambiar institución, contenidos, idioma, identidad
visual y proveedor de alojamiento. Lo que no debería perder es la separación
entre verificación formal automática y evaluación pedagógica humana.

## Camino corto

1. En GitHub, usar **Fork** sobre el repositorio público.
2. En el fork, cambiar nombre y descripción del repositorio.
3. Desplegarlo con el botón de Railway del `README`, o con el `Dockerfile` en
   cualquier proveedor que admita contenedores y PostgreSQL.
4. Abrir `/accounts/instalar/` y completar el asistente inicial.
5. Entrar al administrador para elegir idioma, nombre, colores y traducciones.
6. Instalar prácticas compartidas desde sus ZIP o construir un banco propio.

El despliegue no copia estudiantes, intentos ni datos de investigación del
proyecto original. Cada fork comienza con una base vacía.

## Mantener la historia necesaria

No hace falta copiar conversaciones privadas ni credenciales para conservar el
aprendizaje del proyecto. La continuidad pública vive en:

- `WHITE_PAPER.md`: marco pedagógico;
- `AGENTS.md`: principios y límites obligatorios;
- `ARCHITECTURE.md`: mapa técnico;
- `MEMORY.md`: decisiones y bitácora;
- `README.md`: estado funcional y operación;
- `docs/PAQUETES.md`: contrato para compartir contenidos;
- este archivo y `CONTRIBUTING.md`: continuidad entre equipos.

Cada fork debería mantener esos documentos al día y agregar sus propias
decisiones situadas, sin presentar la experiencia local como regla universal.

## Recibir mejoras del proyecto original

GitHub permite sincronizar un fork desde la interfaz. Antes de integrar una
actualización:

1. hacer backup de PostgreSQL;
2. leer las migraciones y el final de `MEMORY.md`;
3. probar en una rama y, si existe, en un entorno de ensayo;
4. verificar al menos un recorrido estudiante y uno docente;
5. recién entonces desplegar.

Los paquetes ZIP son independientes de Git: sirven para intercambiar contenidos
entre instalaciones aunque sus códigos hayan evolucionado por separado. El
campo `version` del paquete permite rechazar formatos futuros incompatibles sin
corromper datos.

Las traducciones fijas de la interfaz viven en archivos gettext `.po`/`.mo`, no
en el código. Las consignas y descripciones, en cambio, son contenido docente y
se cargan desde el admin. Ver `docs/TRADUCCIONES.md` antes de sumar un idioma.
