"""Management command para insertar la práctica 'Ciencia, conocimiento y método'.

Uso:
    python manage.py insertar_practica_ciencia_conocimiento
    python manage.py insertar_practica_ciencia_conocimiento --dry-run

Inserta una práctica nueva con 3 ejercicios de formalización y 2 de tabla de verdad,
basados en los textos de Bunge y Sabino de la Unidad 1 de IPC.

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

TITULO_PRACTICA = "Ciencia, conocimiento y método"

EJERCICIOS = [
    {
        "tipo": "formalizacion",
        "enunciado": (
            "Según Mario Bunge, el conocimiento científico es verificable: "
            "si una hipótesis fáctica supera las pruebas de la experiencia, "
            "puede considerarse provisoriamente verdadera. "
            "Formalizá esa afirmación usando el diccionario de variables propuesto."
        ),
        "formula_solucion": "E -> V",
        "diccionario_solucion": {
            "E": "La hipótesis fáctica supera las pruebas de la experiencia",
            "V": "La hipótesis puede considerarse provisoriamente verdadera",
        },
        "nota": "Condicional directo — Bunge, verificabilidad (formalización)",
    },
    {
        "tipo": "formalizacion",
        "enunciado": (
            "Bunge sostiene que si el conocimiento científico es racional "
            "y además sus enunciados son verificables mediante la experiencia, "
            "entonces estamos ante conocimiento fáctico genuino. "
            "Formalizá esa afirmación usando el diccionario de variables propuesto."
        ),
        "formula_solucion": "(R & V) -> F",
        "diccionario_solucion": {
            "R": "El conocimiento científico es racional",
            "V": "Sus enunciados son verificables mediante la experiencia",
            "F": "Estamos ante conocimiento fáctico genuino",
        },
        "nota": "Antecedente conjuntivo — Bunge, racionalidad y verificabilidad (formalización)",
    },
    {
        "tipo": "formalizacion",
        "enunciado": (
            "Según Carlos Sabino, si en una investigación se introducen prejuicios del sujeto "
            "y las proposiciones no pueden ser verificadas por otros, entonces la objetividad "
            "no se alcanza. "
            "Formalizá esa afirmación usando el diccionario de variables propuesto."
        ),
        "formula_solucion": "(P & ~V) -> ~O",
        "diccionario_solucion": {
            "P": "Se introducen prejuicios del sujeto en la investigación",
            "V": "Las proposiciones pueden ser verificadas por otros",
            "O": "Se alcanza la objetividad científica",
        },
        "nota": "Antecedente conjuntivo con negaciones — Sabino, objetividad (formalización)",
    },
    {
        "tipo": "tabla_verdad",
        "enunciado": (
            "Bunge sostiene que si el conocimiento científico es metódico, entonces sus hipótesis "
            "están sujetas a prueba empírica. El conocimiento científico es metódico. "
            "Por lo tanto, sus hipótesis están sujetas a prueba empírica. "
            "Determiná si la conclusión se sigue necesariamente de las premisas, "
            "completá la tabla de verdad y justificá tu juicio de validez."
        ),
        "formula_solucion": json.dumps([
            {"formula": "M -> P", "tipo": "premisa"},
            {"formula": "M", "tipo": "premisa"},
            {"formula": "P", "tipo": "conclusion"},
        ], ensure_ascii=False),
        "diccionario_solucion": {
            "M": "El conocimiento científico es metódico",
            "P": "Las hipótesis están sujetas a prueba empírica",
        },
        "nota": "Modus Ponens — Bunge, método científico (tabla de verdad, VÁLIDO)",
    },
    {
        "tipo": "tabla_verdad",
        "enunciado": (
            "Sabino señala que si la ciencia es objetiva, sus afirmaciones pueden ser verificadas "
            "por otros. Las afirmaciones de esta teoría pueden ser verificadas por otros. "
            "Por lo tanto, esta teoría es objetiva. "
            "Determiná si la conclusión se sigue necesariamente de las premisas, "
            "completá la tabla de verdad y justificá tu juicio de validez."
        ),
        "formula_solucion": json.dumps([
            {"formula": "O -> V", "tipo": "premisa"},
            {"formula": "V", "tipo": "premisa"},
            {"formula": "O", "tipo": "conclusion"},
        ], ensure_ascii=False),
        "diccionario_solucion": {
            "O": "La ciencia es objetiva",
            "V": "Las afirmaciones de la teoría pueden ser verificadas por otros",
        },
        "nota": "Afirmación del consecuente — Sabino, objetividad (tabla de verdad, INVÁLIDO)",
    },
]


class Command(BaseCommand):
    help = (
        "Crea la práctica 'Ciencia, conocimiento y método' en el banco común "
        "e inserta 3 ejercicios de formalización y 2 de tabla de verdad "
        "basados en Bunge y Sabino (Unidad 1 IPC), con el usuario "
        f"'{AUTOR_USERNAME}' como autor."
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

        # ── 2. Verificar que la práctica no exista ya ──────────────────────
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
