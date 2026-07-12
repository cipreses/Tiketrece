from django.db import transaction
from django.core.exceptions import ValidationError
from tickets.models import Ticket

@transaction.atomic
def desactivar_sector(sector, actor):
    # Verify permissions: only directivos or superadmins can manage sectors
    if not (actor.rol == 'directivo' or actor.es_superadmin):
        raise ValidationError("No tienes permisos para desactivar sectores.")
        
    # RF-16: Cannot deactivate a sector that has open (non-closed) tickets
    open_tickets_count = Ticket.objects.filter(sector=sector).exclude(estado='cerrado').count()
    if open_tickets_count > 0:
        raise ValidationError(
            f"No se puede desactivar el sector '{sector.nombre}' porque tiene {open_tickets_count} ticket(s) abierto(s)."
        )
        
    sector.activo = False
    sector.save()
    return sector

@transaction.atomic
def activar_sector(sector, actor):
    if not (actor.rol == 'directivo' or actor.es_superadmin):
        raise ValidationError("No tienes permisos para activar sectores.")
    
    sector.activo = True
    sector.save()
    return sector
