from django.db import models
from django.conf import settings

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
