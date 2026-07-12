from django.db import models
from django.core.exceptions import ValidationError

class Sector(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Sector'
        verbose_name_plural = 'Sectores'

    def clean(self):
        # RF-16: Cannot deactivate a sector that has open (non-closed) tickets
        if not self.activo and self.pk:
            from tickets.models import Ticket
            open_tickets_count = Ticket.objects.filter(sector=self).exclude(estado='cerrado').count()
            if open_tickets_count > 0:
                raise ValidationError(
                    f"No se puede desactivar el sector '{self.nombre}' porque tiene {open_tickets_count} ticket(s) abierto(s)."
                )
        super().clean()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre
