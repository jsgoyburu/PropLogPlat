"""Management command para insertar ejercicios de formalización del condicional.

Uso:
    python manage.py insertar_ejercicios_condicional
    python manage.py insertar_ejercicios_condicional --practica-titulo "Condicional"

Explorará la práctica encontrada, mostrará sus ejercicios actuales e insertará
10 nuevos ejercicios de tipo formalizacion sobre la implicación material,
con contextos de razonamiento científico y distintas formas lingüísticas
del condicional (suficiencia, necesidad, "solo si", anidamiento, etc.).
"""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from ejercicios.models import Ejercicio, EjercicioPractica, Practica

Usuario = get_user_model()

# ---------------------------------------------------------------------------
# Ejercicios a insertar
#
# Cada ejercicio cubre una forma lingüística distinta del condicional y
# usa letras mayúsculas indicativas de cada proposición simple.
#
# Formas cubiertas:
#   1. Condicional directo "si… entonces"              →  C -> T
#   2. "Solo si" (necesaria expresada en consecuente)  →  I -> V
#   3. Condición suficiente compuesta  (A & B) -> C    →  (T & E) -> R
#   4. Condición necesaria  A -> B                     →  V -> A
#   5. Condicional anidado  A -> (~B -> C)             →  T -> (~A -> E)
#   6. Antecedente conjuntivo, consecuente disyuntivo   →  (C & M) -> (N | G)
#   7. "Siempre que"                                   →  P -> S
#   8. Condicional con negación en ambos lados ~A->~C  →  ~M -> ~C
#   9. Disyunción en el antecedente  (A | B) -> ~C     →  (A | Q) -> ~T
#  10. Disyunción anidada de conjunciones              →  ((V & P) | D) -> F
# ---------------------------------------------------------------------------

EJERCICIOS_NUEVOS = [
    {
        # Forma: condicional directo "si… entonces"
        # Contexto: ecología / cambio climático
        "enunciado": (
            "Si la concentración atmosférica de CO₂ aumenta, "
            "la temperatura promedio global sube."
        ),
        "formula_solucion": "C -> T",
        "diccionario_solucion": {
            "C": "La concentración atmosférica de CO₂ aumenta",
            "T": "La temperatura promedio global sube",
        },
        "nota": "Condicional directo — ecología",
    },
    {
        # Forma: "solo si" — A solo si B  →  A -> B
        # Contexto: epidemiología / inmunidad de rebaño
        "enunciado": (
            "Una vacuna genera inmunidad de rebaño solo si la proporción "
            "de personas vacunadas supera el umbral crítico de la población."
        ),
        "formula_solucion": "I -> V",
        "diccionario_solucion": {
            "I": "La vacuna genera inmunidad de rebaño",
            "V": "La proporción de personas vacunadas supera el umbral crítico",
        },
        "nota": "'Solo si' — epidemiología",
    },
    {
        # Forma: condición suficiente compuesta  (A y B) -> C
        # Contexto: bioquímica / enzimas
        "enunciado": (
            "La presencia de temperatura adecuada y de la enzima catalítica "
            "es condición suficiente para que se produzca la reacción bioquímica."
        ),
        "formula_solucion": "(T & E) -> R",
        "diccionario_solucion": {
            "T": "La temperatura es adecuada",
            "E": "La enzima catalítica está presente",
            "R": "Se produce la reacción bioquímica",
        },
        "nota": "Condición suficiente compuesta — bioquímica",
    },
    {
        # Forma: condición necesaria  B es necesario para A  →  A -> B
        # Contexto: astrobiología / búsqueda de vida extraterrestre
        "enunciado": (
            "Para que exista vida en un planeta tal como la conocemos, "
            "es condición necesaria que haya agua en estado líquido."
        ),
        "formula_solucion": "V -> A",
        "diccionario_solucion": {
            "V": "Existe vida en el planeta",
            "A": "Hay agua en estado líquido en el planeta",
        },
        "nota": "Condición necesaria — astrobiología",
    },
    {
        # Forma: condicional anidado  T -> (~A -> E)
        # Contexto: neurociencia / estrés postraumático
        "enunciado": (
            "Si una persona estuvo expuesta a un trauma severo, entonces, "
            "en caso de no haber recibido apoyo social oportuno, "
            "desarrollará síntomas de estrés postraumático."
        ),
        "formula_solucion": "T -> (~A -> E)",
        "diccionario_solucion": {
            "T": "La persona estuvo expuesta a un trauma severo",
            "A": "La persona recibió apoyo social oportuno",
            "E": "La persona desarrollará síntomas de estrés postraumático",
        },
        "nota": "Condicional anidado — neurociencia",
    },
    {
        # Forma: antecedente conjuntivo, consecuente disyuntivo  (A & B) -> (C | D)
        # Contexto: astrofísica / evolución estelar
        "enunciado": (
            "Si una estrella agota su combustible nuclear y tiene más de "
            "ocho masas solares, entonces colapsará en una estrella de "
            "neutrones o en un agujero negro."
        ),
        "formula_solucion": "(C & M) -> (N | G)",
        "diccionario_solucion": {
            "C": "La estrella agota su combustible nuclear",
            "M": "La estrella tiene más de ocho masas solares",
            "N": "La estrella colapsa en una estrella de neutrones",
            "G": "La estrella colapsa en un agujero negro",
        },
        "nota": "Antecedente conjuntivo, consecuente disyuntivo — astrofísica",
    },
    {
        # Forma: "siempre que A, B"  →  A -> B
        # Contexto: geología / sismología
        "enunciado": (
            "Siempre que la presión tectónica supera el límite de ruptura "
            "de la corteza, se genera un sismo."
        ),
        "formula_solucion": "P -> S",
        "diccionario_solucion": {
            "P": "La presión tectónica supera el límite de ruptura de la corteza",
            "S": "Se genera un sismo",
        },
        "nota": "'Siempre que' — sismología",
    },
    {
        # Forma: condicional con negación en ambos lados  ~A -> ~C
        # Contexto: farmacología / biodisponibilidad
        "enunciado": (
            "Si el fármaco no es metabolizado correctamente por el hígado, "
            "no alcanzará la concentración terapéutica en sangre."
        ),
        "formula_solucion": "~M -> ~C",
        "diccionario_solucion": {
            "M": "El fármaco es metabolizado correctamente por el hígado",
            "C": "El fármaco alcanza la concentración terapéutica en sangre",
        },
        "nota": "Negación en antecedente y consecuente — farmacología",
    },
    {
        # Forma: disyunción en el antecedente  (A | B) -> ~C
        # Contexto: termodinámica / transferencia de calor
        "enunciado": (
            "Si el sistema está aislado térmicamente o ha alcanzado el "
            "equilibrio térmico con su entorno, entonces no habrá "
            "transferencia neta de calor."
        ),
        "formula_solucion": "(A | Q) -> ~T",
        "diccionario_solucion": {
            "A": "El sistema está aislado térmicamente",
            "Q": "El sistema ha alcanzado el equilibrio térmico con su entorno",
            "T": "Hay transferencia neta de calor",
        },
        "nota": "Disyunción en el antecedente — termodinámica",
    },
    {
        # Forma: disyunción anidada de conjunciones  ((V & P) | D) -> F
        # Contexto: biología evolutiva / fijación de alelos
        "enunciado": (
            "Si una mutación es ventajosa y la presión selectiva es alta, "
            "o bien si la deriva génica actúa sobre una población pequeña, "
            "entonces el alelo puede fijarse en la población."
        ),
        "formula_solucion": "((V & P) | D) -> F",
        "diccionario_solucion": {
            "V": "La mutación es ventajosa",
            "P": "La presión selectiva es alta",
            "D": "La deriva génica actúa sobre una población pequeña",
            "F": "El alelo puede fijarse en la población",
        },
        "nota": "Disyunción de conjunciones en el antecedente — biología evolutiva",
    },
]


class Command(BaseCommand):
    help = (
        "Explora la práctica 'Condicional (Implicación Material)' e inserta "
        "10 ejercicios nuevos de formalización que cubren distintas formas "
        "lingüísticas del condicional en contextos científicos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--practica-titulo",
            default="Condicional",
            help=(
                "Término de búsqueda (icontains) para encontrar la práctica. "
                "Por defecto: 'Condicional'."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra qué se insertaría sin modificar la base de datos.",
        )

    def handle(self, *args, **options):
        titulo_busqueda = options["practica_titulo"]
        dry_run = options["dry_run"]

        # ── 1. Buscar la práctica ──────────────────────────────────────────
        practicas = Practica.objects.filter(titulo__icontains=titulo_busqueda)
        if not practicas.exists():
            raise CommandError(
                f"No se encontró ninguna práctica con título que contenga "
                f"'{titulo_busqueda}'. Verificá que la práctica existe en la "
                f"base de datos de Railway."
            )
        if practicas.count() > 1:
            self.stdout.write(
                self.style.WARNING(
                    f"Se encontraron {practicas.count()} prácticas. "
                    f"Se usará la primera:"
                )
            )
            for p in practicas:
                self.stdout.write(f"  [{p.pk}] {p.titulo}")

        practica = practicas.first()
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Práctica encontrada: [{practica.pk}] \"{practica.titulo}\""
            )
        )

        # ── 2. Explorar ejercicios existentes ──────────────────────────────
        asignaciones = (
            EjercicioPractica.objects.filter(practica=practica)
            .select_related("ejercicio")
            .order_by("orden")
        )

        self.stdout.write(
            f"\nEjercicios actuales en la práctica ({asignaciones.count()}):"
        )
        if asignaciones.exists():
            for ep in asignaciones:
                tipo_label = ep.ejercicio.get_tipo_display()
                enunciado_corto = ep.ejercicio.enunciado[:80].replace("\n", " ")
                sufijo = "..." if len(ep.ejercicio.enunciado) > 80 else ""
                self.stdout.write(
                    f"  [{ep.orden}] ({tipo_label}) {enunciado_corto}{sufijo}"
                )
                self.stdout.write(
                    f"        formula: {ep.ejercicio.formula_solucion}"
                )
        else:
            self.stdout.write("  (ninguno)")

        max_orden = (
            asignaciones.aggregate(max_orden=Max("orden"))["max_orden"] or 0
        )

        # ── 3. Mostrar ejercicios a insertar ───────────────────────────────
        self.stdout.write(f"\nEjercicios a insertar ({len(EJERCICIOS_NUEVOS)}):")
        for i, ej in enumerate(EJERCICIOS_NUEVOS, start=1):
            orden_nuevo = max_orden + i
            self.stdout.write(
                f"  [{orden_nuevo}] {ej['nota']}"
            )
            self.stdout.write(
                f"        formula: {ej['formula_solucion']}"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\n[DRY RUN] No se realizaron cambios en la base de datos."
                )
            )
            return

        # ── 4. Insertar ejercicios ─────────────────────────────────────────
        docente = Usuario.objects.filter(is_superuser=True).first()

        with transaction.atomic():
            insertados = []
            for i, datos in enumerate(EJERCICIOS_NUEVOS, start=1):
                orden_nuevo = max_orden + i
                ejercicio = Ejercicio.objects.create(
                    enunciado=datos["enunciado"],
                    formula_solucion=datos["formula_solucion"],
                    tipo="formalizacion",
                    creado_por=docente,
                    es_publico=False,
                    diccionario_solucion=datos["diccionario_solucion"],
                )
                EjercicioPractica.objects.create(
                    practica=practica,
                    ejercicio=ejercicio,
                    orden=orden_nuevo,
                )
                insertados.append((orden_nuevo, datos["nota"], ejercicio.pk))

        # ── 5. Resumen ─────────────────────────────────────────────────────
        self.stdout.write(
            self.style.SUCCESS("\n✓ Ejercicios insertados exitosamente:")
        )
        for orden, nota, ej_pk in insertados:
            self.stdout.write(f"  [{orden}] Ejercicio #{ej_pk} — {nota}")

        total_ahora = EjercicioPractica.objects.filter(practica=practica).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nTotal de ejercicios en la práctica ahora: {total_ahora}"
            )
        )
