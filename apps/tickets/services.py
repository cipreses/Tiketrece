from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Ticket, Comentario, HistorialTicket

def es_gestor_o_autor(usuario, ticket):
    """
    Checks if the user is the author of the ticket, a directivo,
    or an agent assigned to the ticket's current sector.
    """
    if usuario == ticket.autor:
        return True
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario.rol == 'agente' and usuario.sectores.filter(id=ticket.sector_id).exists():
        return True
    return False

@transaction.atomic
def crear_ticket(autor, sector, prioridad, titulo, descripcion):
    if not sector.activo:
        raise ValidationError("No se puede crear un ticket en un sector desactivado.")
    
    ticket = Ticket.objects.create(
        autor=autor,
        sector=sector,
        prioridad=prioridad,
        titulo=titulo,
        descripcion=descripcion,
        estado='abierto'
    )
    return ticket

@transaction.atomic
def cambiar_estado(ticket, nuevo_estado, actor):
    old_estado = ticket.estado
    
    if old_estado == nuevo_estado:
        return ticket

    # State Machine Valid Transitions
    VALID_TRANSITIONS = {
        ('abierto', 'en_progreso'),
        ('abierto', 'en_espera'),
        ('en_progreso', 'en_espera'),
        ('en_progreso', 'resuelto'),
        ('en_espera', 'en_progreso'),
        ('resuelto', 'cerrado'),
        ('cerrado', 'en_progreso'),
    }

    if (old_estado, nuevo_estado) not in VALID_TRANSITIONS:
        raise ValidationError(f"Transición de estado inválida: {old_estado} -> {nuevo_estado}")

    # Cierre / Reapertura Guard (exige autor o gestor)
    if nuevo_estado == 'cerrado' or old_estado == 'cerrado':
        if not es_gestor_o_autor(actor, ticket):
            raise ValidationError("Solo el autor o un gestor del sector/directivo pueden cerrar o reabrir el ticket.")
    else:
        # Standard transitions (requires agent of the sector or directivo)
        if not (actor.rol == 'directivo' or actor.es_superadmin):
            if actor.rol == 'agente':
                if not actor.sectores.filter(id=ticket.sector_id).exists():
                    raise ValidationError("Un agente solo puede modificar tickets de sus sectores.")
            else:
                raise ValidationError("No tienes permisos para modificar el estado de este ticket.")

    # Apply change
    ticket.estado = nuevo_estado
    if nuevo_estado == 'cerrado':
        ticket.cerrado_en = timezone.now()
    else:
        ticket.cerrado_en = None
        
    ticket.save()

    # Audit log
    HistorialTicket.objects.create(
        ticket=ticket,
        actor=actor,
        tipo='estado',
        valor_anterior=old_estado,
        valor_nuevo=nuevo_estado
    )
    return ticket

@transaction.atomic
def cambiar_prioridad(ticket, nueva_prioridad, actor):
    old_prioridad = ticket.prioridad
    if old_prioridad == nueva_prioridad:
        return ticket

    # Validate choices
    if nueva_prioridad not in dict(Ticket.PRIORIDADES):
        raise ValidationError("Prioridad inválida.")

    # Authorization Check
    if not (actor.rol == 'directivo' or actor.es_superadmin):
        if actor.rol == 'agente':
            if not actor.sectores.filter(id=ticket.sector_id).exists():
                raise ValidationError("Un agente solo puede cambiar la prioridad en tickets de sus sectores.")
        else:
            raise ValidationError("No tienes permisos para cambiar la prioridad de este ticket.")

    ticket.prioridad = nueva_prioridad
    ticket.save()

    # Audit log
    HistorialTicket.objects.create(
        ticket=ticket,
        actor=actor,
        tipo='prioridad',
        valor_anterior=old_prioridad,
        valor_nuevo=nueva_prioridad
    )
    return ticket

@transaction.atomic
def derivar_ticket(ticket, nuevo_sector, actor):
    old_sector = ticket.sector
    if old_sector == nuevo_sector:
        return ticket

    if not nuevo_sector.activo:
        raise ValidationError("No se puede derivar a un sector desactivado.")

    # Authorization Check (for Agent derivation, must be owner sector)
    if not (actor.rol == 'directivo' or actor.es_superadmin):
        if actor.rol == 'agente':
            if not actor.sectores.filter(id=old_sector.id).exists():
                raise ValidationError("Un agente solo puede derivar tickets de sus propios sectores.")
        else:
            raise ValidationError("No tienes permisos para derivar este ticket.")

    ticket.sector = nuevo_sector
    ticket.derivado_desde_sector = old_sector
    ticket.save()

    # Audit log
    HistorialTicket.objects.create(
        ticket=ticket,
        actor=actor,
        tipo='sector',
        valor_anterior=old_sector.nombre,
        valor_nuevo=nuevo_sector.nombre
    )
    return ticket

@transaction.atomic
def reasignar_sector(ticket, nuevo_sector, actor):
    """
    Directivo administrative override to reassign any ticket to another sector (RF-08).
    """
    old_sector = ticket.sector
    if old_sector == nuevo_sector:
        return ticket

    if not nuevo_sector.activo:
        raise ValidationError("No se puede reasignar a un sector desactivado.")

    # Explicit directivo check
    if not (actor.rol == 'directivo' or actor.es_superadmin):
        raise ValidationError("Solo un directivo puede reasignar un ticket de forma administrativa.")

    ticket.sector = nuevo_sector
    ticket.derivado_desde_sector = old_sector
    ticket.save()

    # Audit log
    HistorialTicket.objects.create(
        ticket=ticket,
        actor=actor,
        tipo='sector',
        valor_anterior=old_sector.nombre,
        valor_nuevo=nuevo_sector.nombre
    )
    return ticket

@transaction.atomic
def agregar_comentario(ticket, autor, texto):
    if not texto.strip():
        raise ValidationError("El comentario no puede estar vacío.")

    # Rule of "relacionado" validation (RF-10)
    es_relacionado = False
    if autor.rol == 'directivo' or autor.es_superadmin:
        es_relacionado = True
    elif autor == ticket.autor:
        es_relacionado = True
    elif autor.rol == 'agente' and autor.sectores.filter(id=ticket.sector_id).exists():
        es_relacionado = True

    if not es_relacionado:
        raise ValidationError("No tienes permisos para comentar en este ticket porque no está relacionado con tu rol o alcance.")

    comentario = Comentario.objects.create(
        ticket=ticket,
        autor=autor,
        texto=texto
    )
    return comentario
