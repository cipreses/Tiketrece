from django.core.management.base import BaseCommand
from sectores.models import Sector

class Command(BaseCommand):
    help = "Semilla los sectores iniciales del sistema si no existen."

    def handle(self, *args, **options):
        sectores_iniciales = [
            ("Secretaría", "Área administrativa y de secretaría académica."),
            ("TI", "Tecnología de la Información y soporte de infraestructura."),
            ("Mantenimiento", "Mantenimiento general de las instalaciones."),
            ("Talleres", "Gestión y soporte técnico en los talleres industriales."),
            ("Laboratorio", "Soporte y gestión de laboratorios químicos y físicos."),
            ("Equipo Directivo", "Conducción institucional y gobernanza general."),
            ("Preceptorías", "Gestión de alumnos, preceptoría y asistencia."),
            ("Regencia", "Regencia docente y organización pedagógica.")
        ]

        created_count = 0
        for nombre, descripcion in sectores_iniciales:
            sector, created = Sector.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": descripcion, "activo": True}
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Sector creado: {nombre}"))
            else:
                self.stdout.write(self.style.WARNING(f"El sector {nombre} ya existe."))

        self.stdout.write(self.style.SUCCESS(f"Se crearon {created_count} sectores nuevos."))
