# Cómo continuar PropLogPlat

Este proyecto está pensado para que docentes, desarrolladorxs y agentes de IA
puedan adaptarlo sin perder el sentido pedagógico que le dio origen.

## Antes de cambiar algo

1. Leer `AGENTS.md`: sus principios pedagógicos tienen prioridad sobre la
   conveniencia técnica.
2. Leer el final de `MEMORY.md`: allí está el estado real del trabajo reciente.
3. Consultar `ARCHITECTURE.md` para ubicar el cambio.
4. Crear una rama breve y descriptiva; no trabajar directamente sobre la rama
   principal.

## Flujo recomendado, incluso para “vibe coding”

1. Explicar el problema en lenguaje docente y describir qué experiencia de
   aprendizaje debería mejorar.
2. Pedir al agente que cite los archivos y pruebas que leyó antes de modificar.
3. Hacer un cambio incremental y observable.
4. Ejecutar `python manage.py check` y los tests del módulo afectado.
5. Revisar la pantalla como estudiante y como docente.
6. Actualizar `README.md` si cambió el uso y siempre registrar la intervención
   en `MEMORY.md` con el formato obligatorio.

No se aceptan cambios que automaticen la aprobación pedagógica, clasifiquen
estudiantes o oculten sus procesos de razonamiento. La máquina verifica y hace
visible; el juicio pedagógico sigue siendo humano.

## Entorno de desarrollo

Con Python 3.13 o superior:

```bash
python -m venv .venv
python -m pip install -r requirements-dev.txt
python manage.py migrate
python manage.py runserver
```

También se puede usar el entorno reproducible:

```bash
docker compose up --build
```

Luego abrir `http://localhost:8000/accounts/instalar/`. La clave inicial del
entorno local de Compose es `change-me-before-production`; nunca debe usarse en
un servidor público.

## Checks mínimos

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Las contribuciones deben incluir tests cuando cambian comportamiento. Un cambio
de textos, documentación o estilos puede justificar una comprobación visual en
lugar de un test automatizado, pero debe quedar anotado en `MEMORY.md`.

## Cómo pedir ayuda a un agente

Un buen pedido contiene:

- situación de clase que motiva el cambio;
- personas afectadas y rol desde el que se usa la pantalla;
- comportamiento actual y esperado;
- límites pedagógicos que no deben cruzarse;
- evidencia disponible (captura, intentos, práctica de ejemplo);
- pedido explícito de tests y actualización de `MEMORY.md`.

El agente debe detenerse si una decisión puede cambiar la evaluación, la
privacidad o el significado de una analítica y no hay criterio docente explícito.
