# Despliegue e instalación

## Railway — camino recomendado

El template público crea dos servicios: la aplicación y PostgreSQL. Genera
`SECRET_KEY` y solicita una `SETUP_TOKEN` privada. La configuración del
repositorio ejecuta migraciones antes de arrancar y verifica `/healthz/`.

Después del primer despliegue:

1. abrir la URL pública seguida de `/accounts/instalar/`;
2. pegar la `SETUP_TOKEN` elegida al desplegar;
3. crear la cuenta administradora y elegir nombre e idioma;
4. guardar la URL de `/admin/`.

El asistente se cierra de forma permanente al completar esos pasos.

## Cualquier proveedor con contenedores

El `Dockerfile` incluye la aplicación y los archivos estáticos. Se necesita una
base PostgreSQL administrada y estas variables:

- `SECRET_KEY`: valor aleatorio largo;
- `SETUP_TOKEN`: clave temporal privada para el asistente;
- `DEBUG=False`;
- `ALLOWED_HOSTS`: dominio público sin `https://`;
- `DATABASE_URL`: URL PostgreSQL completa;
- `PORT`: opcional, el proveedor suele inyectarla.

El contenedor ejecuta migraciones idempotentes antes de iniciar Gunicorn. Para
múltiples réplicas, es preferible configurar la migración como tarea previa del
proveedor y usar el comando de inicio de `railway.toml`.

## Prueba local reproducible

```bash
docker compose up --build
```

Abrir `http://localhost:8000/accounts/instalar/` y usar la clave local indicada
en `docker-compose.yml`. Ese archivo es solo para desarrollo: antes de exponer
una instancia hay que reemplazar todos sus valores de ejemplo.

## Copias de seguridad

Antes de actualizar código o ejecutar migraciones en una instalación con uso
real, crear una copia de PostgreSQL desde el proveedor. Los paquetes de
prácticas no reemplazan un backup: deliberadamente no contienen personas,
intentos ni progreso.
