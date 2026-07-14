from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Ticket, Comentario, HistorialTicket, Notificacion
from .permissions import es_gestor_o_autor, puede_asignar_agente

from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def send_emails_safe(recipients_list, ticket, subject, message):
    """
    Sends emails individually to recipients in recipients_list who have recibir_emails=True.
    Safe against SMTP exceptions to avoid transaction rollback or breaking request flow.
    """
    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
    for recipient in recipients_list:
        if getattr(recipient, 'recibir_emails', True) and recipient.email:
            body = (
                f"Hola {recipient.first_name or recipient.username},\n\n"
                f"El ticket #{ticket.id} tiene una novedad:\n"
                f"{message}\n\n"
                f"Podés ver los detalles ingresando al siguiente enlace:\n"
                f"{site_url}/tickets/{ticket.id}/\n\n"
                f"Saludos,\nEl equipo de Tiketrece"
            )
            try:
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient.email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(
                    f"Error al enviar email a {recipient.email} para el ticket #{ticket.id}: {str(e)}"
                )

def create_notifications(ticket, actor, tipo, mensaje, origin_sector=None, dest_sector=None):
    """
    Creates notifications in bulk for relevant active users (author + agents of origin/destination sectors)
    excluding the actor performing the change to prevent self-notification.
    """
    if not origin_sector:
        origin_sector = ticket.sector

    recipients = set()

    # 1. Ticket author (if active)
    if ticket.autor.is_active:
        recipients.add(ticket.autor)

    # 2. Origin sector agents (must be active and have agente role)
    for agent in origin_sector.agentes.filter(rol='agente', is_active=True):
        recipients.add(agent)

    # 3. Destination sector agents (must be active and specified)
    if dest_sector:
        for agent in dest_sector.agentes.filter(rol='agente', is_active=True):
            recipients.add(agent)

    # 4. Exclude the actor of the change (no self-notification)
    recipients.discard(actor)

    # Bulk create Notificacion objects
    notifications_to_create = []
    for r in recipients:
        notifications_to_create.append(Notificacion(
            destinatario=r,
            ticket=ticket,
            tipo=tipo,
            mensaje=mensaje
        ))
    if notifications_to_create:
        Notificacion.objects.bulk_create(notifications_to_create)

    # Queue email notifications on commit
    tipo_map = {
        'estado': 'cambió de estado',
        'prioridad': 'cambió de prioridad',
        'sector': 'cambió de sector',
        'comentario': 'nuevo comentario',
    }
    action_desc = tipo_map.get(tipo, 'actualización')
    subject = f"[Tiketrece] Ticket #{ticket.id} — {action_desc}"
    
    # Convert recipients set to a list
    recipients_list = list(recipients)
    
    transaction.on_commit(lambda: send_emails_safe(recipients_list, ticket, subject, mensaje))

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

    # Generate Notification
    mensaje = f"El estado del ticket #{ticket.id} cambió a '{nuevo_estado}'."
    create_notifications(ticket, actor, 'estado', mensaje)

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

    # Generate Notification
    mensaje = f"La prioridad del ticket #{ticket.id} cambió a '{nueva_prioridad}'."
    create_notifications(ticket, actor, 'prioridad', mensaje)

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

    # Audit auto-clear of agent if present
    if ticket.agente_asignado:
        HistorialTicket.objects.create(
            ticket=ticket,
            actor=actor,
            tipo='asignacion',
            valor_anterior=ticket.agente_asignado.email,
            valor_nuevo='—'
        )
    ticket.agente_asignado = None

    # Apply change
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

    # Generate Notification
    mensaje = f"El ticket #{ticket.id} fue derivado al sector '{nuevo_sector.nombre}'."
    create_notifications(ticket, actor, 'sector', mensaje, origin_sector=old_sector, dest_sector=nuevo_sector)

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

    # Audit auto-clear of agent if present
    if ticket.agente_asignado:
        HistorialTicket.objects.create(
            ticket=ticket,
            actor=actor,
            tipo='asignacion',
            valor_anterior=ticket.agente_asignado.email,
            valor_nuevo='—'
        )
    ticket.agente_asignado = None

    # Apply change
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

    # Generate Notification
    mensaje = f"El ticket #{ticket.id} fue reasignado al sector '{nuevo_sector.nombre}' por un directivo."
    create_notifications(ticket, actor, 'sector', mensaje, origin_sector=old_sector, dest_sector=nuevo_sector)

    return ticket

@transaction.atomic
def agregar_comentario(ticket, autor, texto):
    if not texto.strip():
        raise ValidationError("El comentario no puede estar vacío.")

    # Rule of "relacionado" validation (RF-10)
    if not es_gestor_o_autor(autor, ticket):
        raise ValidationError("No tienes permisos para comentar en este ticket porque no está relacionado con tu rol o alcance.")

    comentario = Comentario.objects.create(
        ticket=ticket,
        autor=autor,
        texto=texto
    )

    # Generate Notification
    mensaje = f"Nuevo comentario de {autor.first_name or autor.email} en el ticket #{ticket.id}."
    create_notifications(ticket, autor, 'comentario', mensaje)

    return comentario


@transaction.atomic
def asignar_agente(ticket, agente, actor):
    """
    Assigns an agent to a ticket. If agente is None, it deassigns the ticket.
    """
    # 1. Authorization check
    if not puede_asignar_agente(actor, ticket):
        raise ValidationError("No tienes permisos para asignar agentes en este ticket.")
        
    # 2. Validation check of the new agent
    if agente is not None:
        if agente.rol != 'agente':
            raise ValidationError("El usuario asignado debe tener el rol de agente.")
        if not agente.sectores.filter(id=ticket.sector_id).exists():
            raise ValidationError("El agente no pertenece al sector del ticket.")
            
    old_agente = ticket.agente_asignado
    if old_agente == agente:
        return ticket
        
    # Apply change
    ticket.agente_asignado = agente
    ticket.save()
    
    # Audit log
    old_email = old_agente.email if old_agente else '—'
    new_email = agente.email if agente else '—'
    
    HistorialTicket.objects.create(
        ticket=ticket,
        actor=actor,
        tipo='asignacion',
        valor_anterior=old_email,
        valor_nuevo=new_email
    )
    
    # Notify only if a new agent was assigned (agente is not None) AND actor is not assigning themselves
    if agente is not None and actor != agente:
        mensaje = f"Fuiste asignado como agente al ticket #{ticket.id} por {actor.first_name or actor.email}."
        # Generate Notification
        Notificacion.objects.create(
            destinatario=agente,
            ticket=ticket,
            tipo='asignacion',
            mensaje=mensaje
        )
        
        # Enqueue email notification post-commit
        subject = f"[Tiketrece] Ticket #{ticket.id} — asignación de agente"
        recipients_list = [agente]
        
        # We call the existing send_emails_safe in services.py
        transaction.on_commit(lambda: send_emails_safe(recipients_list, ticket, subject, mensaje))
        
    return ticket
