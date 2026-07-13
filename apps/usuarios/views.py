import urllib.parse
import requests
import secrets
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponse, JsonResponse
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.http import require_POST
from usuarios.models import Usuario
from usuarios.services import cambiar_rol, cambiar_estado_activo
from sectores.models import Sector

def directivo_required(view_func):
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not (request.user.rol == 'directivo' or request.user.es_superadmin):
            return HttpResponseForbidden("Acceso denegado. Se requieren privilegios directivos.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST' and getattr(settings, 'ENABLE_MOCK_AUTH', False):
        email = request.POST.get('email', '').strip()
        name = request.POST.get('name', '').strip()
        # Mock auth via backend
        try:
            user = authenticate(request, mock_email=email, mock_name=name)
            if user:
                auth_login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, "Error de autenticación simulada.")
        except PermissionDenied as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error inesperado: {str(e)}")

    return render(request, 'login.html', {
        'enable_mock_auth': getattr(settings, 'ENABLE_MOCK_AUTH', False),
        'google_client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.REDIRECT_URI
    })

def google_login_redirect(request):
    # Set state in session for CSRF check
    state = secrets.token_urlsafe(32)
    request.session['oauth_state'] = state
    
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'hd': '13dejulio.edu.ar'
    })
    return redirect(auth_url)

def google_login_callback(request):
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    # CSRF Check
    stored_state = request.session.pop('oauth_state', None)
    if not state or state != stored_state:
        raise PermissionDenied("Fallo en verificación CSRF de OAuth state.")
        
    if not code:
        raise PermissionDenied("No se recibió código de autorización de Google.")
        
    # Exchange authorization code for token
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        'code': code,
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'redirect_uri': settings.REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=10)
        if not response.ok:
            raise PermissionDenied("Fallo al intercambiar el código por tokens con Google.")
        
        tokens = response.json()
        id_token = tokens.get('id_token')
        
        user = authenticate(request, token=id_token)
        if user:
            auth_login(request, user)
            return redirect('dashboard')
        else:
            raise PermissionDenied("No se pudo iniciar sesión con las credenciales de Google.")
    except PermissionDenied as e:
        messages.error(request, str(e))
        return redirect('login')
    except Exception as e:
        messages.error(request, f"Error de conexión con Google: {str(e)}")
        return redirect('login')

def logout_view(request):
    auth_logout(request)
    return redirect('login')

@directivo_required
def usuarios_list_view(request):
    usuarios = Usuario.objects.all().order_by('email')
    sectores = Sector.objects.filter(activo=True)
    return render(request, 'usuarios/admin.html', {
        'usuarios': usuarios,
        'sectores': sectores,
        'roles': ['solicitante', 'agente', 'directivo']
    })

@directivo_required
@require_POST
def cambiar_rol_view(request, usuario_id):
    usuario_afectado = get_object_or_404(Usuario, pk=usuario_id)
    nuevo_rol = request.POST.get('rol')
    
    try:
        cambiar_rol(usuario_afectado, nuevo_rol, request.user)
        messages.success(request, f"Rol de {usuario_afectado.email} cambiado a {nuevo_rol} exitosamente.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

@directivo_required
@require_POST
def cambiar_activo_view(request, usuario_id):
    usuario_afectado = get_object_or_404(Usuario, pk=usuario_id)
    is_active_str = request.POST.get('activo')
    is_active = is_active_str == 'true'
    
    try:
        cambiar_estado_activo(usuario_afectado, is_active, request.user)
        estado_str = "activado" if is_active else "desactivado"
        messages.success(request, f"Usuario {usuario_afectado.email} {estado_str} exitosamente.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

@directivo_required
@require_POST
def asignar_sector_view(request, usuario_id):
    usuario_afectado = get_object_or_404(Usuario, pk=usuario_id)
    if usuario_afectado.rol != 'agente':
        messages.error(request, "Solo los agentes pueden tener sectores asignados.")
        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        
    sector_id = request.POST.get('sector_id')
    sector = get_object_or_404(Sector, pk=sector_id)
    
    from usuarios.models import UsuarioSector
    try:
        UsuarioSector.objects.get_or_create(usuario=usuario_afectado, sector=sector)
        messages.success(request, f"Sector {sector.nombre} asignado a {usuario_afectado.email}.")
    except Exception as e:
        messages.error(request, f"Error al asignar sector: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

@directivo_required
@require_POST
def desasignar_sector_view(request, usuario_id):
    usuario_afectado = get_object_or_404(Usuario, pk=usuario_id)
    sector_id = request.POST.get('sector_id')
    sector = get_object_or_404(Sector, pk=sector_id)
    
    from usuarios.models import UsuarioSector
    try:
        UsuarioSector.objects.filter(usuario=usuario_afectado, sector=sector).delete()
        messages.success(request, f"Sector {sector.nombre} desasignado de {usuario_afectado.email}.")
    except Exception as e:
        messages.error(request, f"Error al desasignar sector: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
