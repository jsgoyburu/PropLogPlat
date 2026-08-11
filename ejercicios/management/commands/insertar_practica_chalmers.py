"""Management command para insertar la práctica 'CHALMERS - Observación, hechos y experimento'.

Uso:
    python manage.py insertar_practica_chalmers
    python manage.py insertar_practica_chalmers --dry-run

Inserta una práctica nueva con 3 ejercicios de formalización y 2 de tabla de verdad,
basados en el capítulo 1 y el capítulo 3 de Chalmers, ¿Qué es esa cosa llamada ciencia?

La práctica y los ejercicios se agregan al banco común (es_publica=True,
es_publico=True) con el usuario 'jsgoyburu' como autor.
"""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ejercicios.models import Ejercicio, EjercicioPractica, Practica

Usuario = get_user_model()

AUTOR_USERNAME = "jsgoyburu"

TITULO_PRACTICA = "CHALMERS - Observación, hechos y experimento"

EJERCICIOS = [
    {
        "tipo": "formalizacion",
        "enunciado": (
            "Según Chalmers, la opinión común sobre la ciencia sostiene que si los hechos "
            "de la experiencia son dados directamente a través de los sentidos, entonces "
            "dos observadores que enfrentan la misma escena tendrán experiencias visuales "
            "idénticas. Formalizá esa afirmación usando el diccionario de variables propuesto."
        ),
        "formula_solucion": "D -> I",
        "diccionario_solucion": {
            "D": "Los hechos de la experiencia son dados directamente a través de los sentidos",
            "I": "Dos observadores que enfrentan la misma escena tienen experiencias visuales idénticas",
        },
        "nota": "Condicional directo — Chalmers, la opinión común sobre la observación (formalización)",
    },
    {
        "tipo": "formalizacion",
        "enunciado": (
            "Chalmers argumenta que para formular un enunciado observacional significativo, "
            "el observador necesita dominar el entramado conceptual apropiado y saber aplicarlo. "
            "Si no domina ese entramado, no puede formular enunciados observacionales adecuados. "
            "Formalizá esa afirmación usando el diccionario de variables propuesto."
        ),
        "formula_solucion": "~E -> ~F",
        "diccionario_solucion": {
            "E": "El observador domina el entramado conceptual apropiado",
            "F": "El observador puede formular enunciados observacionales adecuados",
        },
        "nota": "Condicional con negaciones — Chalmers, enunciados observacionales y conocimiento previo (formalización)",
    },
    {
        "tipo": "formalizacion",
        "enunciado": (
            "Para Chalmers, si los enunciados observacionales son falibles y además dependen "
            "del conocimiento previo, entonces la base observacional de la ciencia no es "
            "segura ni directa. Formalizá esa afirmación usando el diccionario de variables "
            "propuesto."
        ),
        "formula_solucion": "(F & D) -> ~S",
        "diccionario_solucion": {
            "F": "Los enunciados observacionales son falibles",
            "D": "Los enunciados observacionales dependen del conocimiento previo",
            "S": "La base observacional de la ciencia es segura y directa",
        },
        "nota": "Antecedente conjuntivo con negación en consecuente — Chalmers, falibilidad observacional (formalización)",
    },
    {
        "tipo": "tabla_verdad",
        "enunciado": (
            "Chalmers argumenta que si las experiencias perceptuales estuvieran determinadas "
            "únicamente por las imágenes en la retina, entonces los observadores que enfrentan "
            "la misma escena tendrían experiencias perceptuales idénticas. Sin embargo, los "
            "observadores que enfrentan la misma escena no tienen experiencias perceptuales "
            "idénticas. Por lo tanto, las experiencias perceptuales no están determinadas "
            "únicamente por las imágenes en la retina. "
            "Determiná si la conclusión se sigue necesariamente de las premisas, "
            "completá la tabla de verdad y justificá tu juicio de validez."
        ),
        "formula_solucion": json.dumps([
            {"formula": "R -> I", "tipo": "premisa"},
            {"formula": "~I", "tipo": "premisa"},
            {"formula": "~R", "tipo": "conclusion"},
        ], ensure_ascii=False),
        "diccionario_solucion": {
            "R": "Las experiencias perceptuales están determinadas únicamente por las imágenes en la retina",
            "I": "Los observadores que enfrentan la misma escena tienen experiencias perceptuales idénticas",
        },
        "nota": "Modus Tollens — Chalmers, ver es creer (tabla de verdad, VÁLIDO)",
    },
    {
        "tipo": "tabla_verdad",
        "enunciado": (
            "Chalmers muestra, con el caso de Hertz, que si los resultados experimentales "
            "constituyen una base adecuada para la ciencia, entonces son objetivos y "
            "repetibles. Los resultados de Hertz sobre los rayos catódicos eran objetivos "
            "y repetibles. Por lo tanto, los resultados de Hertz constituían una base "
            "adecuada para la ciencia. "
            "Determiná si la conclusión se sigue necesariamente de las premisas, "
            "completá la tabla de verdad y justificá tu juicio de validez."
        ),
        "formula_solucion": json.dumps([
            {"formula": "A -> R", "tipo": "premisa"},
            {"formula": "R", "tipo": "premisa"},
            {"formula": "A", "tipo": "conclusion"},
        ], ensure_ascii=False),
        "diccionario_solucion": {
            "A": "Los resultados experimentales constituyen una base adecuada para la ciencia",
            "R": "Los resultados experimentales son objetivos y repetibles",
        },
        "nota": "Afirmación del consecuente — Chalmers, experimento de Hertz (tabla de verdad, INVÁLIDO)",
    },
]


class Command(BaseCommand):
    help = (
        "Crea la práctica 'CHALMERS - Observación, hechos y experimento' en el banco común "
        "e inserta 3 ejercicios de formalización y 2 de tabla de verdad "
        "basados en Chalmers, ¿Qué es esa cosa llamada ciencia?, caps. 1 y 3, "
        f"con el usuario '{AUTOR_USERNAME}' como autor."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra qué se insertaría sin modificar la base de datos.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # ── 1. Buscar el usuario autor ─────────────────────────────────────
        try:
            autor = Usuario.objects.get(username=AUTOR_USERNAME)
        except Usuario.DoesNotExist:
            raise CommandError(
                f"No se encontró el usuario '{AUTOR_USERNAME}'. "
                f"Verificá que el username existe en la base de datos de Railway."
            )
        self.stdout.write(
            self.style.SUCCESS(f"\n✓ Autor: [{autor.pk}] {autor.username}")
        )

        # ── 2. Verificar que la práctica pública no exista ya ──────────────
        if Practica.objects.filter(titulo=TITULO_PRACTICA, es_publica=True).exists():
            raise CommandError(
                f"Ya existe una práctica pública con el título '{TITULO_PRACTICA}'. "
                f"Si querés volver a crearla, eliminá la existente del banco común primero."
            )

        # ── 3. Mostrar resumen ─────────────────────────────────────────────
        self.stdout.write(f'\nPráctica a crear: "{TITULO_PRACTICA}" (banco común)')
        self.stdout.write(f"\nEjercicios a insertar ({len(EJERCICIOS)}):")
        for i, ej in enumerate(EJERCICIOS, start=1):
            self.stdout.write(f"  [{i}] ({ej['tipo']}) {ej['nota']}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\n[DRY RUN] No se realizaron cambios en la base de datos."
                )
            )
            return

        # ── 4. Crear práctica y ejercicios ────────────────────────────────
        with transaction.atomic():
            practica = Practica.objects.create(
                titulo=TITULO_PRACTICA,
                creada_por=autor,
                es_publica=True,   # banco común: visible a todos los docentes
            )

            insertados = []
            for i, datos in enumerate(EJERCICIOS, start=1):
                ejercicio = Ejercicio.objects.create(
                    enunciado=datos["enunciado"],
                    formula_solucion=datos["formula_solucion"],
                    tipo=datos["tipo"],
                    creado_por=autor,
                    es_publico=True,   # banco común
                    diccionario_solucion=datos["diccionario_solucion"],
                )
                EjercicioPractica.objects.create(
                    practica=practica,
                    ejercicio=ejercicio,
                    orden=i,
                )
                insertados.append((i, datos["nota"], ejercicio.pk))

        # ── 5. Resumen ─────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Práctica creada: [{practica.pk}] "{practica.titulo}"'
        ))
        self.stdout.write(self.style.SUCCESS("\n✓ Ejercicios insertados:"))
        for orden, nota, ej_pk in insertados:
            self.stdout.write(f"  [{orden}] Ejercicio #{ej_pk} — {nota}")
