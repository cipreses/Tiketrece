from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Usuario, HistorialRol

@transaction.atomic
def cambiar_rol(usuario_afectado, nuevo_rol, actor):
    if nuevo_rol not in ['solicitante', 'agente', 'directivo']:
        raise ValidationError("Rol inválido.")

    old_rol = usuario_afectado.rol
    if old_rol == nuevo_rol:
        return usuario_afectado

    # Governance rule (b): Superadmin cannot be degraded by a non-superadmin
    if usuario_afectado.es_superadmin and not actor.es_superadmin:
        raise ValidationError("Un no-superadmin no puede modificar el rol de un superadmin.")

    # Governance rule (a): The system must never be left without active directivos
    if old_rol == 'directivo' and nuevo_rol != 'directivo':
        # Check if there are other active directivos
        other_active_directivos = Usuario.objects.filter(rol='directivo', is_active=True).exclude(id=usuario_afectado.id).exists()
        if not other_active_directivos:
            raise ValidationError("No se puede degradar al único directivo activo del sistema.")

    # Apply change
    usuario_afectado.rol = nuevo_rol
    usuario_afectado.save()

    # Audit log (c)
    HistorialRol.objects.create(
        usuario=usuario_afectado,
        actor=actor,
        rol_anterior=old_rol,
        rol_nuevo=nuevo_rol
    )
    return usuario_afectado

@transaction.atomic
def cambiar_estado_activo(usuario_afectado, is_active, actor):
    if usuario_afectado.is_active == is_active:
        return usuario_afectado

    # Governance rule (b): Superadmin cannot be deactivated by a non-superadmin
    if usuario_afectado.es_superadmin and not actor.es_superadmin:
        raise ValidationError("Un no-superadmin no puede cambiar el estado de un superadmin.")

    # Governance rule (a): The system must never be left without active directivos
    if usuario_afectado.rol == 'directivo' and not is_active:
        other_active_directivos = Usuario.objects.filter(rol='directivo', is_active=True).exclude(id=usuario_afectado.id).exists()
        if not other_active_directivos:
            raise ValidationError("No se puede desactivar al único directivo activo del sistema.")

    usuario_afectado.is_active = is_active
    usuario_afectado.save()
    return usuario_afectado
