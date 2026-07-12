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


def puede_ver_ticket(usuario, ticket):
    if not usuario.is_authenticated:
        return False
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario.rol == 'agente':
        return usuario.sectores.filter(id=ticket.sector_id).exists()
    return ticket.autor == usuario


def puede_comentar_ticket(usuario, ticket):
    """
    RF-10 (relacionado):
    - Solicitante: only on their own tickets.
    - Agente: only on tickets of their sector(s).
    - Directivo/Superadmin: global.
    """
    if not usuario.is_authenticated:
        return False
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario == ticket.autor:
        return True
    if usuario.rol == 'agente':
        return usuario.sectores.filter(id=ticket.sector_id).exists()
    return False


def puede_cambiar_estado(usuario, ticket):
    """
    State changes:
    - Agente: only if ticket belongs to their sector.
    - Directivo/Superadmin: global.
    - Solicitante: can only close/reopen their own tickets (close must be from resuelto).
    """
    if not usuario.is_authenticated:
        return False
    if usuario.rol == 'directivo' or usuario.es_superadmin:
        return True
    if usuario.rol == 'agente' and usuario.sectores.filter(id=ticket.sector_id).exists():
        return True
    # Solicitante close/reopen check (must be the author)
    if usuario == ticket.autor:
        # State machine validations themselves are checked in service layers,
        # but author is allowed to close (from resuelto) or reopen (from cerrado)
        return True
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
