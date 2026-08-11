"""Management command para insertar ejercicios de argumentos en una práctica.

Uso:
    python manage.py insertar_ejercicios_argumentos
    python manage.py insertar_ejercicios_argumentos --practica-titulo "Argumentos"

Explorará la práctica encontrada, mostrará sus ejercicios actuales e insertará
6 nuevos ejercicios de tipo tabla_verdad sobre validez de argumentos.
"""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from ejercicios.models import Ejercicio, EjercicioPractica, Practica

Usuario = get_user_model()

EJERCICIOS_NUEVOS = [
    {
        "enunciado": (
            "En climatología se sostiene que si la temperatura global aumenta, "
            "los glaciares se derriten. Los registros muestran que la temperatura "
            "global ha aumentado. Por lo tanto, los glaciares se están derritiendo."
        ),
        "formula_solucion": [
            {"formula": "p -> q", "tipo": "premisa"},
            {"formula": "p", "tipo": "premisa"},
            {"formula": "q", "tipo": "conclusion"},
        ],
        "diccionario_solucion": {
            "p": "La temperatura global aumenta",
            "q": "Los glaciares se derriten",
        },
        "nota": "Modus Ponens — ecología (VÁLIDO)",
    },
    {
        "enunciado": (
            "Todo organismo que realiza fotosíntesis produce oxígeno como subproducto. "
            "Este organismo no produce oxígeno. "
            "Por lo tanto, este organismo no realiza fotosíntesis."
        ),
        "formula_solucion": [
            {"formula": "p -> q", "tipo": "premisa"},
            {"formula": "~q", "tipo": "premisa"},
            {"formula": "~p", "tipo": "conclusion"},
        ],
        "diccionario_solucion": {
            "p": "El organismo realiza fotosíntesis",
            "q": "El organismo produce oxígeno",
        },
        "nota": "Modus Tollens — biología (VÁLIDO)",
    },
    {
        "enunciado": (
            "Estudios en ciencias políticas sugieren que si aumenta la desigualdad "
            "económica, crece la conflictividad social. A su vez, si crece la "
            "conflictividad social, se debilitan las instituciones democráticas. "
            "De esto se concluye que si aumenta la desigualdad económica, se "
            "debilitan las instituciones democráticas."
        ),
        "formula_solucion": [
            {"formula": "p -> q", "tipo": "premisa"},
            {"formula": "q -> r", "tipo": "premisa"},
            {"formula": "p -> r", "tipo": "conclusion"},
        ],
        "diccionario_solucion": {
            "p": "Aumenta la desigualdad económica",
            "q": "Crece la conflictividad social",
            "r": "Se debilitan las instituciones democráticas",
        },
        "nota": "Silogismo Hipotético — ciencias sociales (VÁLIDO)",
    },
    {
        "enunciado": (
            "El cuadro clínico del paciente tiene origen bacteriano o viral. "
            "Los análisis de laboratorio descartaron el origen bacteriano. "
            "Por lo tanto, el cuadro clínico tiene origen viral."
        ),
        "formula_solucion": [
            {"formula": "p | q", "tipo": "premisa"},
            {"formula": "~p", "tipo": "premisa"},
            {"formula": "q", "tipo": "conclusion"},
        ],
        "diccionario_solucion": {
            "p": "El cuadro clínico tiene origen bacteriano",
            "q": "El cuadro clínico tiene origen viral",
        },
        "nota": "Silogismo Disyuntivo — epidemiología (VÁLIDO)",
    },
    {
        "enunciado": (
            "La hipótesis del impacto meteorítico predice que si un gran meteorito "
            "impactó la Tierra hace 66 millones de años, entonces debería encontrarse "
            "una capa de iridio en los estratos geológicos de ese período. "
            "Se encontró esa capa de iridio. "
            "Por lo tanto, un gran meteorito impactó la Tierra."
        ),
        "formula_solucion": [
            {"formula": "p -> q", "tipo": "premisa"},
            {"formula": "q", "tipo": "premisa"},
            {"formula": "p", "tipo": "conclusion"},
        ],
        "diccionario_solucion": {
            "p": "Un gran meteorito impactó la Tierra hace 66 millones de años",
            "q": "Existe una capa de iridio en los estratos geológicos de ese período",
        },
        "nota": "Afirmación del consecuente — geología (INVÁLIDO, falacia)",
    },
    {
        "enunciado": (
            "En psicolingüística se sostiene que si un niño recibe input lingüístico "
            "abundante durante el período crítico, entonces adquiere el lenguaje con "
            "normalidad. Este niño no recibió input lingüístico abundante durante el "
            "período crítico. Por lo tanto, este niño no adquirió el lenguaje con normalidad."
        ),
        "formula_solucion": [
            {"formula": "p -> q", "tipo": "premisa"},
            {"formula": "~p", "tipo": "premisa"},
            {"formula": "~q", "tipo": "conclusion"},
        ],
        "diccionario_solucion": {
            "p": "El niño recibió input lingüístico abundante durante el período crítico",
            "q": "El niño adquirió el lenguaje con normalidad",
        },
        "nota": "Negación del antecedente — lingüística (INVÁLIDO, falacia)",
    },
]


class Command(BaseCommand):
    help = (
        "Explora la práctica 'Argumentos' en la base de datos e inserta "
        "6 ejercicios nuevos de validez de argumentos por tabla de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--practica-titulo",
            default="Argumento",
            help=(
                "Término de búsqueda (icontains) para encontrar la práctica. "
                "Por defecto: 'Argumento'."
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
        asignaciones = EjercicioPractica.objects.filter(
            practica=practica
        ).select_related("ejercicio").order_by("orden")

        self.stdout.write(
            f"\nEjercicios actuales en la práctica ({asignaciones.count()}):"
        )
        if asignaciones.exists():
            for ep in asignaciones:
                tipo_label = ep.ejercicio.get_tipo_display()
                self.stdout.write(
                    f"  [{ep.orden}] ({tipo_label}) "
                    + ep.ejercicio.enunciado[:80].replace("\n", " ")
                    + ("..." if len(ep.ejercicio.enunciado) > 80 else "")
                )
        else:
            self.stdout.write("  (ninguno)")

        max_orden = asignaciones.aggregate(max_orden=Max("orden"))["max_orden"] or 0

        # ── 3. Mostrar ejercicios a insertar ───────────────────────────────
        self.stdout.write(f"\nEjercicios a insertar (6):")
        for i, ej in enumerate(EJERCICIOS_NUEVOS, start=1):
            orden_nuevo = max_orden + i
            self.stdout.write(
                f"  [{orden_nuevo}] {ej['nota']}"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n[DRY RUN] No se realizaron cambios en la base de datos.")
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
                    formula_solucion=json.dumps(
                        datos["formula_solucion"], ensure_ascii=False
                    ),
                    tipo="tabla_verdad",
                    creado_por=docente,
                    es_publico=False,
                    diccionario_solucion=datos["diccionario_solucion"],
                )
                ep = EjercicioPractica.objects.create(
                    practica=practica,
                    ejercicio=ejercicio,
                    orden=orden_nuevo,
                )
                insertados.append((orden_nuevo, datos["nota"], ejercicio.pk))

        # ── 5. Resumen ─────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("\n✓ Ejercicios insertados exitosamente:"))
        for orden, nota, ej_pk in insertados:
            self.stdout.write(f"  [{orden}] Ejercicio #{ej_pk} — {nota}")

        total_ahora = EjercicioPractica.objects.filter(practica=practica).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nTotal de ejercicios en la práctica ahora: {total_ahora}"
            )
        )
