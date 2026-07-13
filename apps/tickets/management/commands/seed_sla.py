from django.core.management.base import BaseCommand
from tickets.models import PrioridadSLA

class Command(BaseCommand):
    help = 'Seeds the default SLA target hours for priorities'

    def handle(self, *args, **options):
        defaults = {
            'urgente': 4,
            'alta': 24,
            'media': 72,
            'baja': 168
        }
        for prio, hours in defaults.items():
            obj, created = PrioridadSLA.objects.get_or_create(
                prioridad=prio,
                defaults={'horas_objetivo': hours}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Creada prioridad SLA '{prio}' con {hours} horas."))
            else:
                self.stdout.write(f"Prioridad SLA '{prio}' ya existe con {obj.horas_objetivo} horas.")
