"""Comando de management para gestionar research_id en estudiantes existentes.

Reglas:
  - consentimiento_investigacion=True  → genera research_id si falta
  - consentimiento_investigacion=False → anula research_id si tiene uno
  - consentimiento_investigacion=None  → anula research_id si tiene uno
                                         (pendiente de responder consentimiento)

Uso:
    python manage.py poblar_research_id            # ejecuta y aplica cambios
    python manage.py poblar_research_id --dry-run  # solo reporta, no modifica
"""

import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Usuario


class Command(BaseCommand):
    help = 'Pobla o anula research_id en estudiantes según su consentimiento de investigación.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué haría sin aplicar ningún cambio.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('-- DRY RUN: no se modificara ningun registro --\n'))

        estudiantes = Usuario.objects.filter(es_docente=False, is_staff=False)

        # Segmentar por estado de consentimiento
        con_consent = estudiantes.filter(consentimiento_investigacion=True)
        sin_consent = estudiantes.filter(consentimiento_investigacion=False)
        pendientes = estudiantes.filter(consentimiento_investigacion=None)

        # Calcular qué acciones se van a tomar
        necesitan_research_id = con_consent.filter(research_id=None)
        tienen_id_indebido_false = sin_consent.exclude(research_id=None)
        tienen_id_indebido_none = pendientes.exclude(research_id=None)

        self._reportar_estado(
            con_consent, sin_consent, pendientes,
            necesitan_research_id, tienen_id_indebido_false, tienen_id_indebido_none,
        )

        if dry_run:
            return

        generados = self._generar_research_ids(necesitan_research_id)
        anulados = self._anular_research_ids(tienen_id_indebido_false | tienen_id_indebido_none)

        self.stdout.write('')
        if generados:
            self.stdout.write(self.style.SUCCESS(f'  OK {generados} research_id generados'))
        if anulados:
            self.stdout.write(self.style.SUCCESS(f'  OK {anulados} research_id anulados'))
        if not generados and not anulados:
            self.stdout.write(self.style.SUCCESS('  OK Nada que hacer, todo consistente.'))

    # ─── helpers ──────────────────────────────────────────────────────────────

    def _reportar_estado(
        self,
        con_consent, sin_consent, pendientes,
        necesitan_id, indebidos_false, indebidos_none,
    ):
        total = con_consent.count() + sin_consent.count() + pendientes.count()
        self.stdout.write(f'\nEstudiantes totales: {total}\n')

        self.stdout.write(
            f'  consentimiento=True   : {con_consent.count():>5}  '
            f'(con research_id: {con_consent.exclude(research_id=None).count()}, '
            f'sin research_id: {necesitan_id.count()})'
        )
        self.stdout.write(
            f'  consentimiento=False  : {sin_consent.count():>5}  '
            f'(research_id a anular: {indebidos_false.count()})'
        )
        self.stdout.write(
            f'  consentimiento=None   : {pendientes.count():>5}  '
            f'(research_id a anular: {indebidos_none.count()})'
        )

        pendiente_accion = necesitan_id.count() + indebidos_false.count() + indebidos_none.count()
        if pendiente_accion:
            self.stdout.write(
                self.style.WARNING(f'\nAcciones pendientes: {pendiente_accion} registros')
            )
        else:
            self.stdout.write(self.style.SUCCESS('\nEstado consistente, sin acciones pendientes.'))

    @transaction.atomic
    def _generar_research_ids(self, qs) -> int:
        count = 0
        for usuario in qs.iterator():
            usuario.research_id = uuid.uuid4()
            usuario.save(update_fields=['research_id'])
            count += 1
        return count

    @transaction.atomic
    def _anular_research_ids(self, qs) -> int:
        return qs.update(research_id=None)
