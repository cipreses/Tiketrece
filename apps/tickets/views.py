from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import HttpResponseForbidden, HttpResponse, Http404
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Case, When, Value, IntegerField
from sectores.models import Sector
from tickets.models import Ticket, Comentario, HistorialTicket, Notificacion
from tickets.permissions import (
    obtener_tickets_visibles,
    puede_ver_ticket,
    puede_comentar_ticket,
    puede_cambiar_estado,
    puede_cambiar_prioridad,
    puede_derivar_ticket,
    puede_reasignar_sector
)
from tickets.services import (
    crear_ticket,
    cambiar_estado,
    cambiar_prioridad,
    derivar_ticket,
    reasignar_sector,
    agregar_comentario
)

@login_required
def dashboard_view(request):
    # Retrieve tickets scoped to the user's permissions
    tickets_visibles = obtener_tickets_visibles(request.user)
    
    # Aggregated metrics
    totales_estado = {item['estado']: item['count'] for item in tickets_visibles.values('estado').annotate(count=Count('id'))}
    totales_prioridad = {item['prioridad']: item['count'] for item in tickets_visibles.values('prioridad').annotate(count=Count('id'))}
    totales_sector = {item['sector__nombre']: item['count'] for item in tickets_visibles.values('sector__nombre').annotate(count=Count('id'))}
    
    # Fill defaults for zero states
    for estado, _ in Ticket.ESTADOS:
        totales_estado.setdefault(estado, 0)
    for prioridad, _ in Ticket.PRIORIDADES:
        totales_prioridad.setdefault(prioridad, 0)

    indicadores = {
        'abiertos': totales_estado.get('abierto', 0),
        'en_progreso': totales_estado.get('en_progreso', 0),
        'en_espera': totales_estado.get('en_espera', 0),
        'resueltos': totales_estado.get('resuelto', 0),
        'cerrados': totales_estado.get('cerrado', 0),
        'total': tickets_visibles.count()
    }

    return render(request, 'dashboard.html', {
        'indicadores': indicadores,
        'totales_prioridad': totales_prioridad,
        'totales_sector': totales_sector
    })

@login_required
def tickets_list_view(request):
    # Base visible tickets according to user's role and scope
    tickets = obtener_tickets_visibles(request.user)
    
    # Apply query filters
    sector_id = request.GET.get('sector')
    estado = request.GET.get('estado')
    prioridad = request.GET.get('prioridad')
    autor_email = request.GET.get('autor')
    q = request.GET.get('q', '').strip()
    
    if sector_id:
        tickets = tickets.filter(sector_id=sector_id)
    if estado:
        tickets = tickets.filter(estado=estado)
    if prioridad:
        tickets = tickets.filter(prioridad=prioridad)
    if autor_email:
        tickets = tickets.filter(autor__email__icontains=autor_email)
    if q:
        tickets = tickets.filter(Q(titulo__icontains=q) | Q(descripcion__icontains=q))
        
    # Tickets are ordered by updated_at desc by default (defined in Meta)
    
    sectores = Sector.objects.filter(activo=True)
    
    # If request is HTMX, render only the partial table body
    if request.headers.get('HX-Request'):
        return render(request, 'tickets/partials/ticket_rows.html', {'tickets': tickets})
        
    return render(request, 'tickets/list.html', {
        'tickets': tickets,
        'sectores': sectores,
        'estados': Ticket.ESTADOS,
        'prioridades': Ticket.PRIORIDADES,
        # Keep filter values for prepopulating inputs
        'f_sector': sector_id,
        'f_estado': estado,
        'f_prioridad': prioridad,
        'f_autor': autor_email,
        'f_q': q
    })

@login_required
def ticket_detail_view(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    
    if not puede_ver_ticket(request.user, ticket):
        raise Http404("Ticket no encontrado o sin permisos de acceso.")
        
    comentarios = ticket.comentarios.all().order_by('creado_en')
    historial = ticket.historial.all().order_by('-creado_en')
    sectores = Sector.objects.filter(activo=True)
    
    # Determine allowed transitions based on current state
    transiciones_validas = []
    VALID_TRANSITIONS = {
        ('abierto', 'en_progreso'),
        ('abierto', 'en_espera'),
        ('en_progreso', 'en_espera'),
        ('en_progreso', 'resuelto'),
        ('en_espera', 'en_progreso'),
        ('resuelto', 'cerrado'),
        ('cerrado', 'en_progreso'),
    }
    for old, new in VALID_TRANSITIONS:
        if old == ticket.estado:
            transiciones_validas.append(new)
            
    # Check individual action permissions
    context = {
        'ticket': ticket,
        'comentarios': comentarios,
        'historial': historial,
        'sectores': sectores,
        'estados': Ticket.ESTADOS,
        'prioridades': Ticket.PRIORIDADES,
        'transiciones_validas': transiciones_validas,
        
        # Permissions flags
        'puede_comentar': puede_comentar_ticket(request.user, ticket),
        'puede_cambiar_estado': puede_cambiar_estado(request.user, ticket),
        'puede_cambiar_prioridad': puede_cambiar_prioridad(request.user, ticket),
        'puede_derivar': puede_derivar_ticket(request.user, ticket),
        'puede_reasignar': puede_reasignar_sector(request.user, ticket)
    }
    
    return render(request, 'tickets/detail.html', context)

@login_required
def crear_ticket_view(request):
    if request.method == 'POST':
        sector_id = request.POST.get('sector_id')
        prioridad = request.POST.get('prioridad')
        titulo = request.POST.get('titulo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        
        sector = get_object_or_404(Sector, pk=sector_id)
        
        try:
            ticket = crear_ticket(
                autor=request.user,
                sector=sector,
                prioridad=prioridad,
                titulo=titulo,
                descripcion=descripcion
            )
            messages.success(request, f"Ticket #{ticket.id} creado exitosamente.")
            return redirect('ticket_detail', ticket_id=ticket.id)
        except ValidationError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, f"Error al crear ticket: {str(e)}")
            
    sectores = Sector.objects.filter(activo=True)
    return render(request, 'tickets/crear.html', {
        'sectores': sectores,
        'prioridades': Ticket.PRIORIDADES
    })

@login_required
@require_POST
def cambiar_estado_view(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    nuevo_estado = request.POST.get('estado')
    
    try:
        cambiar_estado(ticket, nuevo_estado, request.user)
        messages.success(request, f"Estado del ticket #{ticket.id} cambiado a '{nuevo_estado}'.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

@login_required
@require_POST
def cambiar_prioridad_view(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    nueva_prioridad = request.POST.get('prioridad')
    
    try:
        cambiar_prioridad(ticket, nueva_prioridad, request.user)
        messages.success(request, f"Prioridad del ticket #{ticket.id} cambiada a '{nueva_prioridad}'.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

@login_required
@require_POST
def derivar_ticket_view(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    nuevo_sector_id = request.POST.get('sector_id')
    nuevo_sector = get_object_or_404(Sector, pk=nuevo_sector_id)
    
    try:
        derivar_ticket(ticket, nuevo_sector, request.user)
        messages.success(request, f"Ticket #{ticket.id} derivado al sector '{nuevo_sector.nombre}'.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

@login_required
@require_POST
def reasignar_sector_view(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    nuevo_sector_id = request.POST.get('sector_id')
    nuevo_sector = get_object_or_404(Sector, pk=nuevo_sector_id)
    
    try:
        reasignar_sector(ticket, nuevo_sector, request.user)
        messages.success(request, f"Ticket #{ticket.id} reasignado al sector '{nuevo_sector.nombre}' de forma directiva.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

@login_required
@require_POST
def agregar_comentario_view(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    texto = request.POST.get('texto', '').strip()
    
    try:
        agregar_comentario(ticket, request.user, texto)
        messages.success(request, "Comentario agregado exitosamente.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})


import csv
from django.http import StreamingHttpResponse

class Echo:
    """An object that implements just the write method of the file-like
    interface and returns the line instead of writing to a file.
    """
    def write(self, value):
        return value

def sanitize_csv_cell(value):
    if not isinstance(value, str):
        return value
    if not value:
        return value
    # CSV Formula Injection defense: prefix with ' if it starts with =, +, -, @, tab, or carriage return
    if value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value

@login_required
def export_tickets_csv_view(request):
    # Base visible tickets according to user's role and scope (CRITICAL: applies first)
    tickets = obtener_tickets_visibles(request.user)
    
    # Apply query filters (exactly like tickets_list_view)
    sector_id = request.GET.get('sector')
    estado = request.GET.get('estado')
    prioridad = request.GET.get('prioridad')
    autor_email = request.GET.get('autor')
    q = request.GET.get('q', '').strip()
    
    if sector_id:
        tickets = tickets.filter(sector_id=sector_id)
    if estado:
        tickets = tickets.filter(estado=estado)
    if prioridad:
        tickets = tickets.filter(prioridad=prioridad)
    if autor_email:
        tickets = tickets.filter(autor__email__icontains=autor_email)
    if q:
        tickets = tickets.filter(Q(titulo__icontains=q) | Q(descripcion__icontains=q))
        
    # Ordered by updated_at desc
    tickets = tickets.order_by('-actualizado_en')
    
    def csv_rows():
        # Excel UTF-8 BOM so Excel opens it with correct accent chars automatically
        yield '\ufeff'
        
        pseudo_buffer = Echo()
        writer = csv.writer(pseudo_buffer)
        
        # Header row
        yield writer.writerow([
            'id', 'titulo', 'sector', 'autor_email', 'prioridad', 'estado', 
            'creado_en', 'actualizado_en', 'cerrado_en'
        ])
        
        for ticket in tickets.select_related('sector', 'autor'):
            yield writer.writerow([
                ticket.id,
                sanitize_csv_cell(ticket.titulo),
                sanitize_csv_cell(ticket.sector.nombre),
                sanitize_csv_cell(ticket.autor.email),
                sanitize_csv_cell(ticket.get_prioridad_display()),
                sanitize_csv_cell(ticket.get_estado_display()),
                ticket.creado_en.strftime('%Y-%m-%d %H:%M:%S') if ticket.creado_en else '',
                ticket.actualizado_en.strftime('%Y-%m-%d %H:%M:%S') if ticket.actualizado_en else '',
                ticket.cerrado_en.strftime('%Y-%m-%d %H:%M:%S') if ticket.cerrado_en else ''
            ])
            
    response = StreamingHttpResponse(csv_rows(), content_type="text/csv; charset=utf-8")
    response['Content-Disposition'] = 'attachment; filename="tickets_export.csv"'
    return response


@login_required
def notificaciones_dropdown_view(request):
    notificaciones = Notificacion.objects.filter(destinatario=request.user)[:10]
    unread_count = Notificacion.objects.filter(destinatario=request.user, leida=False).count()
    return render(request, 'tickets/partials/notification_dropdown.html', {
        'notificaciones': notificaciones,
        'unread_count': unread_count
    })


@login_required
@require_POST
def marcar_leida_notificacion_view(request, notif_id):
    # IDOR check: verify the notification belongs to request.user
    try:
        notificacion = Notificacion.objects.get(pk=notif_id, destinatario=request.user)
    except Notificacion.DoesNotExist:
        raise Http404("Notificación no encontrada.")
        
    notificacion.leida = True
    notificacion.save()
    
    return notificaciones_dropdown_view(request)


@login_required
@require_POST
def marcar_todas_notificaciones_view(request):
    Notificacion.objects.filter(destinatario=request.user, leida=False).update(leida=True)
    return notificaciones_dropdown_view(request)


