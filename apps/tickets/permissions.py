from tickets.models import Ticket

def obtener_tickets_visibles(usuario, base_queryset=None):
    """
    Returns the queryset of tickets visible to the user based on role and scope.
    - Solicitante: Only their own tickets.
    - Agente: Tickets belonging to their assigned sectors.
    - Directivo/Superadmin: Global visibility of all tickets.
    """
    if base_queryset is None:
        base_queryset = Ticket.objects.all()
        
    if not usuario.is_authenticated:
        return Ticket.objects.none()
        
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return base_queryset
        
    if usuario.rol == 'agente':
        return base_queryset.filter(sector__in=usuario.sectores.all())
        
    # Default is solicitante
    return base_queryset.filter(autor=usuario)


def es_gestor_o_autor(usuario, ticket):
    """
    Checks if the user is the author of the ticket, a directivo/superadmin,
    or an agent assigned to the ticket's current sector.
    """
    if not usuario.is_authenticated:
        return False
    if usuario == ticket.autor:
        return True
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario.rol == 'agente' and usuario.sectores.filter(id=ticket.sector_id).exists():
        return True
    return False


def puede_ver_ticket(usuario, ticket):
    return es_gestor_o_autor(usuario, ticket)


def puede_comentar_ticket(usuario, ticket):
    return es_gestor_o_autor(usuario, ticket)


def puede_cambiar_estado(usuario, ticket):
    if not usuario.is_authenticated:
        return False
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario.rol == 'agente' and usuario.sectores.filter(id=ticket.sector_id).exists():
        return True
    # Author (solicitante) can only change state to close (from resuelto) or to reopen (from cerrado)
    if usuario == ticket.autor:
        return ticket.estado in ['resuelto', 'cerrado']
    return False


def puede_cambiar_prioridad(usuario, ticket):
    if not usuario.is_authenticated:
        return False
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario.rol == 'agente':
        return usuario.sectores.filter(id=ticket.sector_id).exists()
    return False


def puede_derivar_ticket(usuario, ticket):
    if not usuario.is_authenticated:
        return False
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario.rol == 'agente':
        return usuario.sectores.filter(id=ticket.sector_id).exists()
    return False


def puede_reasignar_sector(usuario, ticket):
    """
    RF-08: Administrative sector override (Directivo/Superadmin only).
    """
    if not usuario.is_authenticated:
        return False
    return usuario.rol == 'directivo' or usuario.es_superadmin


def puede_gestionar_sectores(usuario):
    """
    Directivo/Superadmin only (Setup).
    """
    if not usuario.is_authenticated:
        return False
    return usuario.rol == 'directivo' or usuario.es_superadmin


def puede_gestionar_roles(usuario):
    """
    Directivo/Superadmin only (Setup).
    """
    if not usuario.is_authenticated:
        return False
    return usuario.rol == 'directivo' or usuario.es_superadmin


def puede_asignar_agente(usuario, ticket):
    if not usuario.is_authenticated:
        return False
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario.rol == 'agente':
        return usuario.sectores.filter(id=ticket.sector_id).exists()
    return False
