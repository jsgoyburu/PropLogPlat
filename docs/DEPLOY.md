# Despliegue e instalación

## Railway — camino recomendado

La configuración de Railway crea dos servicios: la aplicación y PostgreSQL.
El template de PropLogPlat genera `SECRET_KEY` y `SETUP_TOKEN`; el repositorio
ejecuta migraciones antes de arrancar y verifica `/healthz/`.

Después del primer despliegue:

1. abrir la URL pública: una base vacía redirige automáticamente al instalador;
2. revisar el diagnóstico, sin copiar a ningún lado los valores secretos;
3. si falta algo, abrir **Variables** en Railway, crear cada clave indicada,
   pegar su valor y volver a desplegar;
4. volver al diagnóstico y comprobar que el nuevo proceso recibió los cambios;
5. crear la cuenta administradora, la primera cohorte y la identidad local;
6. guardar la URL de `/admin/` en el gestor de contraseñas del equipo.

El asistente se cierra de forma permanente al completar esos pasos. Railway y
otros proveedores administrados no ofrecen una API universal para que la propia
aplicación cambie su entorno; por eso el asistente genera valores e instrucciones
pero no finge haber modificado el panel externo.

## Asistente provider-agnostic

El mismo flujo sirve en Render, Fly.io, Heroku, un contenedor o un VPS. El paso
de entorno permite:

- previsualizar una configuración sin guardarla;
- descargar `proplogplat.env` para copiar sus pares clave/valor;
- escribir `.env` solo cuando se marca explícitamente esa opción y la
  `SETUP_TOKEN` actual es válida.

La última opción es para una computadora propia, VPS o volumen persistente. No
debe usarse como fuente de verdad en filesystems efímeros: el próximo despliegue
puede borrarla. Las variables inyectadas por el sistema operativo o el proveedor
siempre tienen precedencia sobre `.env`. En todos los casos hace falta reiniciar:
un proceso en ejecución no puede reemplazar su propio entorno.

La interfaz completa —ayudas, diagnósticos y validaciones incluidas— usa los
catálogos gettext `.mo` de castellano, inglés, francés, alemán y chino
simplificado.

## Cualquier proveedor con contenedores

El `Dockerfile` incluye la aplicación y los archivos estáticos. Se necesita una
base PostgreSQL administrada y estas variables:

- `SECRET_KEY`: valor aleatorio largo;
- `SETUP_TOKEN`: clave temporal privada para el asistente;
- `DEBUG=False`;
- `ALLOWED_HOSTS`: dominio público sin `https://`;
- `DATABASE_URL`: URL PostgreSQL completa;
- `PORT`: opcional, el proveedor suele inyectarla.

Para ofrecer recuperación de contraseña hay que agregar `BREVO_API_KEY` y un
`DEFAULT_FROM_EMAIL` perteneciente a un dominio autenticado. Sin
`BREVO_API_KEY` ni `EMAIL_HOST`, el correo se imprime en consola: por eso la
interfaz no anuncia el enlace de recuperación hasta detectar un proveedor
configurado. En Railway Free/Trial/Hobby usar la API HTTP de Brevo; sus puertos
SMTP salientes están bloqueados.

El contenedor ejecuta migraciones idempotentes antes de iniciar Gunicorn. Para
múltiples réplicas, es preferible configurar la migración como tarea previa del
proveedor y usar el comando de inicio de `railway.toml`.

## Prueba local reproducible

```bash
docker compose up --build
```

Abrir `http://localhost:8000/`: la primera entrada redirige automáticamente al
instalador. Usar la clave local indicada en `docker-compose.yml`. Ese archivo es
solo para desarrollo: antes de exponer una instancia hay que reemplazar todos
sus valores de ejemplo.

## Copias de seguridad

Antes de actualizar código o ejecutar migraciones en una instalación con uso
real, crear una copia de PostgreSQL desde el proveedor. Los paquetes de
prácticas no reemplazan un backup: deliberadamente no contienen personas,
intentos ni progreso.
