from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import HttpResponseForbidden, HttpResponse
from django.core.exceptions import ValidationError
from sectores.models import Sector
from sectores.services import desactivar_sector, activar_sector
from usuarios.views import directivo_required

@directivo_required
def sectores_list_view(request):
    sectores = Sector.objects.all().order_by('nombre')
    return render(request, 'sectores/admin.html', {
        'sectores': sectores
    })

@directivo_required
@require_POST
def crear_sector_view(request):
    nombre = request.POST.get('nombre', '').strip()
    descripcion = request.POST.get('descripcion', '').strip()
    
    if not nombre:
        messages.error(request, "El nombre del sector es requerido.")
        return redirect('sectores_list')
        
    try:
        Sector.objects.create(nombre=nombre, descripcion=descripcion, activo=True)
        messages.success(request, f"Sector '{nombre}' creado exitosamente.")
    except Exception as e:
        messages.error(request, f"Error al crear el sector: {str(e)}")
        
    return redirect('sectores_list')

@directivo_required
@require_POST
def editar_sector_view(request, sector_id):
    sector = get_object_or_404(Sector, pk=sector_id)
    nombre = request.POST.get('nombre', '').strip()
    descripcion = request.POST.get('descripcion', '').strip()
    
    if not nombre:
        messages.error(request, "El nombre del sector no puede estar vacío.")
        return redirect('sectores_list')
        
    try:
        sector.nombre = nombre
        sector.descripcion = descripcion
        sector.save()
        messages.success(request, f"Sector '{nombre}' actualizado exitosamente.")
    except Exception as e:
        messages.error(request, f"Error al actualizar el sector: {str(e)}")
        
    return redirect('sectores_list')

@directivo_required
@require_POST
def desactivar_sector_view(request, sector_id):
    sector = get_object_or_404(Sector, pk=sector_id)
    try:
        desactivar_sector(sector, request.user)
        messages.success(request, f"Sector '{sector.nombre}' desactivado exitosamente.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error al desactivar el sector: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

@directivo_required
@require_POST
def activar_sector_view(request, sector_id):
    sector = get_object_or_404(Sector, pk=sector_id)
    try:
        activar_sector(sector, request.user)
        messages.success(request, f"Sector '{sector.nombre}' activado exitosamente.")
    except ValidationError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, f"Error al activar el sector: {str(e)}")
        
    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
