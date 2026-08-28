# Traducciones

PropLogPlat usa el sistema gettext estándar de Django. El castellano es la
fuente pedagógica original y la interfaz se ofrece en:

- `es`: castellano;
- `en`: inglés;
- `fr`: francés;
- `de`: alemán;
- `zh-hans`: chino simplificado (directorio gettext `zh_Hans`).

El asistente de primera instalación está localizado por completo: estructura,
inventario de variables, diagnósticos, campos, ayudas, opciones, validaciones y
comentarios del `.env` generado. Sus mensajes usan los prefijos
`ui.installer_*` e `installer.*` dentro de los mismos archivos `.po`/`.mo`; no
hay un diccionario de traducciones paralelo en Python.

## Dos clases de texto

La **interfaz fija** vive en `locale/<idioma>/LC_MESSAGES/django.po`. En
ejecución Django lee exclusivamente el `django.mo` compilado. La etiqueta
`{% ui 'clave' %}` es una envoltura semántica de gettext; no contiene un
catálogo paralelo en Python.

Las **prácticas y consignas** son contenido docente situado. El castellano se
conserva siempre y las traducciones opcionales se editan desde el admin. Si una
traducción está vacía, la plataforma muestra el original. Esos campos también
viajan en los paquetes ZIP/JSON.

## Corregir una traducción

1. Editar el `msgstr` correspondiente en cada `django.po` afectado.
2. Recompilar los catálogos:

   ```bash
   python -m babel.messages.frontend compile -d locale -D django
   ```

3. Versionar juntos `.po` y `.mo`.
4. Ejecutar al menos:

   ```bash
   python manage.py test accounts.tests.CatalogosGettextTests
   ```

La compilación usa Babel, incluido solo en `requirements-dev.txt`; la
aplicación desplegada no necesita Babel porque los `.mo` ya forman parte del
repositorio y de la imagen.

## Agregar un idioma

1. Sumar el código a `LANGUAGES`, `ConfigSitio.IDIOMA_CHOICES`, el asistente y
   el selector de `templates/base.html`.
2. Crear `locale/<locale_gettext>/LC_MESSAGES/django.po`, traducir todas las
   claves y compilar su `.mo`.
3. Si también traducirá contenidos, agregar campos opcionales a `Ejercicio` y
   `Practica`, exponerlos en admin y mantener el lector de paquetes compatible
   con ZIP anteriores.
4. Agregar el idioma a `CatalogosGettextTests` y probar fallback al castellano.

No traducir automáticamente las consignas en tiempo de ejecución: una
traducción pedagógica requiere revisión humana y debe permanecer auditable.
