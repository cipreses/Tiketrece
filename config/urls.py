from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
import usuarios.views as user_views
import sectores.views as sector_views
import tickets.views as ticket_views

def root_redirect(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Root
    path('', root_redirect, name='root'),
    
    # Auth
    path('auth/login/', user_views.login_view, name='login'),
    path('auth/logout/', user_views.logout_view, name='logout'),
    path('auth/google/', user_views.google_login_redirect, name='google_login'),
    path('auth/callback/', user_views.google_login_callback, name='google_callback'),
    
    # Dashboard
    path('dashboard/', ticket_views.dashboard_view, name='dashboard'),
    
    # Tickets
    path('tickets/', ticket_views.tickets_list_view, name='tickets_list'),
    path('tickets/crear/', ticket_views.crear_ticket_view, name='crear_ticket'),
    path('tickets/export/', ticket_views.export_tickets_csv_view, name='export_tickets_csv'),
    path('tickets/sla/', ticket_views.sla_config_view, name='sla_config'),
    
    # Notifications
    path('notifications/', ticket_views.notificaciones_dropdown_view, name='notificaciones_dropdown'),
    path('notifications/<int:notif_id>/read/', ticket_views.marcar_leida_notificacion_view, name='marcar_leida_notificacion'),
    path('notifications/read-all/', ticket_views.marcar_todas_notificaciones_view, name='marcar_todas_notificaciones'),
    
    # Attachments
    path('tickets/<int:ticket_id>/adjuntos/subir/', ticket_views.subir_adjunto_view, name='subir_adjunto'),
    path('adjuntos/<int:adjunto_id>/descargar/', ticket_views.descargar_adjunto_view, name='descargar_adjunto'),
    
    path('tickets/<int:ticket_id>/', ticket_views.ticket_detail_view, name='ticket_detail'),
    path('tickets/<int:ticket_id>/estado/', ticket_views.cambiar_estado_view, name='cambiar_estado'),
    path('tickets/<int:ticket_id>/prioridad/', ticket_views.cambiar_prioridad_view, name='cambiar_prioridad'),
    path('tickets/<int:ticket_id>/derivar/', ticket_views.derivar_ticket_view, name='derivar_ticket'),
    path('tickets/<int:ticket_id>/reasignar/', ticket_views.reasignar_sector_view, name='reasignar_sector'),
    path('tickets/<int:ticket_id>/comentar/', ticket_views.agregar_comentario_view, name='agregar_comentario'),
    
    # Sectores
    path('sectores/', sector_views.sectores_list_view, name='sectores_list'),
    path('sectores/crear/', sector_views.crear_sector_view, name='crear_sector'),
    path('sectores/<int:sector_id>/editar/', sector_views.editar_sector_view, name='editar_sector'),
    path('sectores/<int:sector_id>/desactivar/', sector_views.desactivar_sector_view, name='desactivar_sector'),
    path('sectores/<int:sector_id>/activar/', sector_views.activar_sector_view, name='activar_sector'),
    
    # Usuarios
    path('usuarios/', user_views.usuarios_list_view, name='usuarios_list'),
    path('usuarios/<int:usuario_id>/rol/', user_views.cambiar_rol_view, name='cambiar_rol'),
    path('usuarios/<int:usuario_id>/activo/', user_views.cambiar_activo_view, name='cambiar_activo'),
    path('usuarios/<int:usuario_id>/asignar_sector/', user_views.asignar_sector_view, name='asignar_sector'),
    path('usuarios/<int:usuario_id>/desasignar_sector/', user_views.desasignar_sector_view, name='desasignar_sector'),
]
