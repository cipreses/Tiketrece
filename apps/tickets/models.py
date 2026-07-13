from django.db import models
from django.conf import settings

class PrioridadSLA(models.Model):
    PRIORIDADES = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente'),
    ]
    prioridad = models.CharField(max_length=15, choices=PRIORIDADES, unique=True)
    horas_objetivo = models.PositiveIntegerField()

    class Meta:
        verbose_name = 'Prioridad SLA'
        verbose_name_plural = 'Prioridades SLA'

    def __str__(self):
        return f"{self.get_prioridad_display()}: {self.horas_objetivo} horas"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        Ticket.clear_sla_cache()


class Ticket(models.Model):
    PRIORIDADES = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente'),
    ]

    ESTADOS = [
        ('abierto', 'Abierto'),
        ('en_progreso', 'En Progreso'),
        ('en_espera', 'En Espera'),
        ('resuelto', 'Resuelto'),
        ('cerrado', 'Cerrado'),
    ]

    titulo = models.CharField(max_length=255)
    descripcion = models.TextField()
    sector = models.ForeignKey('sectores.Sector', on_delete=models.PROTECT, related_name='tickets')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='tickets_creados')
    prioridad = models.CharField(max_length=15, choices=PRIORIDADES, default='media')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='abierto')
    
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)
    
    # Trace of the last origin sector before derivation (for convenience)
    derivado_desde_sector = models.ForeignKey(
        'sectores.Sector',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_derivados_desde'
    )

    class Meta:
        ordering = ['-actualizado_en']
        verbose_name = 'Ticket'
        verbose_name_plural = 'Tickets'

    def __str__(self):
        return f"#{self.id}: {self.titulo} ({self.estado})"

    _sla_cache = None

    @classmethod
    def get_sla_dict(cls):
        if cls._sla_cache is None:
            try:
                cls._sla_cache = {p.prioridad: p.horas_objetivo for p in PrioridadSLA.objects.all()}
            except Exception:
                cls._sla_cache = {}
        return cls._sla_cache

    @classmethod
    def clear_sla_cache(cls):
        cls._sla_cache = None

    @property
    def deadline(self):
        sla_dict = Ticket.get_sla_dict()
        defaults = {'urgente': 4, 'alta': 24, 'media': 72, 'baja': 168}
        horas = sla_dict.get(self.prioridad)
        if horas is None:
            horas = defaults.get(self.prioridad, 72)
        from datetime import timedelta
        return self.creado_en + timedelta(hours=horas)

    @property
    def estado_sla(self):
        if self.estado in ['resuelto', 'cerrado']:
            return 'cerrado'
        from django.utils import timezone
        now = timezone.now()
        dl = self.deadline
        if now > dl:
            return 'vencido'
        return 'en_plazo'

    @property
    def sla_texto(self):
        if self.estado in ['resuelto', 'cerrado']:
            return "Cerrado"
        from django.utils import timezone
        now = timezone.now()
        dl = self.deadline
        if now > dl:
            diff = now - dl
            days = diff.days
            hours, remainder = divmod(diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0 or not parts:
                parts.append(f"{minutes}m")
            return f"vencido hace {' '.join(parts)}"
        else:
            diff = dl - now
            days = diff.days
            hours, remainder = divmod(diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0 or not parts:
                parts.append(f"{minutes}m")
            return f"vence en {' '.join(parts)}"


class Comentario(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='comentarios_creados')
    texto = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_en']
        verbose_name = 'Comentario'
        verbose_name_plural = 'Comentarios'

    def __str__(self):
        return f"Comentario de {self.autor} en #{self.ticket.id}"


class HistorialTicket(models.Model):
    TIPOS = [
        ('estado', 'Estado'),
        ('prioridad', 'Prioridad'),
        ('sector', 'Sector'),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='historial')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='historial_tickets')
    creado_en = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=15, choices=TIPOS)
    valor_anterior = models.TextField(null=True, blank=True)
    valor_nuevo = models.TextField()

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'Historial de Ticket'
        verbose_name_plural = 'Historiales de Tickets'

    def __str__(self):
        return f"Cambio {self.tipo} en #{self.ticket.id} por {self.actor}"


class Notificacion(models.Model):
    TIPOS = [
        ('estado', 'Estado'),
        ('prioridad', 'Prioridad'),
        ('sector', 'Sector'),
        ('comentario', 'Comentario'),
    ]

    destinatario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notificaciones')
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='notificaciones')
    tipo = models.CharField(max_length=15, choices=TIPOS)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'

    def __str__(self):
        return f"Notificación ({self.tipo}) para {self.destinatario.email} - Leída: {self.leida}"


import os
import uuid

def ticket_attachment_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ['.pdf', '.jpg', '.jpeg', '.png', '.webp']:
        ext = ''
    safe_name = f"{uuid.uuid4()}{ext}"
    return f"tickets/ticket_{instance.ticket.id}/{safe_name}"


class Adjunto(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='adjuntos')
    archivo = models.FileField(upload_to=ticket_attachment_path)
    nombre_original = models.TextField()
    content_type = models.CharField(max_length=100)
    tamano = models.IntegerField()
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='adjuntos_subidos')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_en']
        verbose_name = 'Archivo Adjunto'
        verbose_name_plural = 'Archivos Adjuntos'

    def __str__(self):
        return f"Adjunto {self.nombre_original} en ticket #{self.ticket.id}"


