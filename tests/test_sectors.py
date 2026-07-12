import pytest
from django.core.exceptions import ValidationError
from sectores.models import Sector
from sectores.services import desactivar_sector
from usuarios.models import Usuario
from tickets.models import Ticket
from tickets.services import crear_ticket, cambiar_estado

@pytest.mark.django_db
class TestSectors:

    @pytest.fixture
    def setup_data(self):
        sector = Sector.objects.create(nombre='Mantenimiento', descripcion='Soporte edilicio', activo=True)
        directivo = Usuario.objects.create(
            username='dir@13dejulio.edu.ar', email='dir@13dejulio.edu.ar',
            first_name='Directivo', google_sub='sub-dir', rol='directivo'
        )
        sol = Usuario.objects.create(
            username='sol@13dejulio.edu.ar', email='sol@13dejulio.edu.ar',
            first_name='Solicitante', google_sub='sub-sol', rol='solicitante'
        )
        return sector, directivo, sol

    def test_deactivation_fails_with_open_tickets_via_service(self, setup_data):
        sector, directivo, sol = setup_data
        
        # Create an open ticket in the sector
        ticket = crear_ticket(
            autor=sol, sector=sector, prioridad='media',
            titulo='Luz quemada', descripcion='Foco del pasillo'
        )
        
        # Attempt to deactivate via service -> should fail
        with pytest.raises(ValidationError) as exc_info:
            desactivar_sector(sector, actor=directivo)
        assert "No se puede desactivar el sector" in str(exc_info.value)
        
        # Verify it remains active
        sector.refresh_from_db()
        assert sector.activo is True

    def test_deactivation_fails_with_open_tickets_via_save(self, setup_data):
        sector, directivo, sol = setup_data
        
        # Create an open ticket
        crear_ticket(
            autor=sol, sector=sector, prioridad='media',
            titulo='Luz quemada', descripcion='Foco del pasillo'
        )
        
        # Attempt to deactivate via direct save -> should fail
        sector.activo = False
        with pytest.raises(ValidationError) as exc_info:
            sector.save()
        assert "No se puede desactivar el sector" in str(exc_info.value)

    def test_deactivation_succeeds_with_only_closed_tickets(self, setup_data):
        sector, directivo, sol = setup_data
        
        # Create a ticket
        ticket = crear_ticket(
            autor=sol, sector=sector, prioridad='media',
            titulo='Luz quemada', descripcion='Foco del pasillo'
        )
        
        # Resolve and Close the ticket
        agente = Usuario.objects.create(
            username='agente@13dejulio.edu.ar', email='agente@13dejulio.edu.ar',
            first_name='Agente', google_sub='sub-agente', rol='agente'
        )
        agente.sectores.add(sector)
        cambiar_estado(ticket, 'en_progreso', actor=agente)
        cambiar_estado(ticket, 'resuelto', actor=agente)
        cambiar_estado(ticket, 'cerrado', actor=sol)
        
        # Deactivate sector via service -> should succeed now
        desactivar_sector(sector, actor=directivo)
        
        sector.refresh_from_db()
        assert sector.activo is False
