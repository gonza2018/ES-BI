"""python manage.py respaldar — crea un respaldo en DATA_DIR/respaldos/ (ver README)."""
from django.core.management.base import BaseCommand

from config.respaldo import crear_respaldo


class Command(BaseCommand):
    help = "Respaldo de bases SQLite y archivos subidos en DATA_DIR/respaldos/"

    def handle(self, *args, **opciones):
        self.stdout.write(self.style.SUCCESS(f"Respaldo creado: {crear_respaldo()}"))
