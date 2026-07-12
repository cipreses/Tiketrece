import pytest
from django.core.exceptions import ValidationError
from sectores.models import Sector
from usuarios.models import Usuario
from tickets.models import Ticket
from tickets.services import crear_ticket, cambiar_estado

@pytest.mark.django_db
class TestTicketFlow:

    @pytest.fixture
    def setup_data(self):
        # Create sector
        sector = Sector.objects.create(nombre='Mantenimiento', descripcion='Soporte edilicio', activo=True)
        # Create users
        solicitante = Usuario.objects.create(
            username='sol@13dejulio.edu.ar', email='sol@13dejulio.edu.ar',
            first_name='Solicitante', google_sub='sub-sol', rol='solicitante'
        )
        agente = Usuario.objects.create(
            username='agente@13dejulio.edu.ar', email='agente@13dejulio.edu.ar',
            first_name='Agente', google_sub='sub-agente', rol='agente'
        )
        # Assign agent to sector
        agente.sectores.add(sector)
        
        directivo = Usuario.objects.create(
            username='dir@13dejulio.edu.ar', email='dir@13dejulio.edu.ar',
            first_name='Directivo', google_sub='sub-dir', rol='directivo'
        )
        
        # Create ticket
        ticket = crear_ticket(
            autor=solicitante, sector=sector, prioridad='media',
            titulo='Vidrio roto', descripcion='Vidrio roto en el salon 3'
        )
        return sector, solicitante, agente, directivo, ticket

    def test_valid_transitions(self, setup_data):
        sector, solicitante, agente, directivo, ticket = setup_data
        
        # abierto -> en_progreso (by agent of the sector)
        cambiar_estado(ticket, 'en_progreso', actor=agente)
        assert ticket.estado == 'en_progreso'
        
        # en_progreso -> en_espera (by agent)
        cambiar_estado(ticket, 'en_espera', actor=agente)
        assert ticket.estado == 'en_espera'
        
        # en_espera -> en_progreso (by agent)
        cambiar_estado(ticket, 'en_progreso', actor=agente)
        assert ticket.estado == 'en_progreso'
        
        # en_progreso -> resuelto (by agent)
        cambiar_estado(ticket, 'resuelto', actor=agente)
        assert ticket.estado == 'resuelto'
        
        # resuelto -> cerrado (by autor)
        cambiar_estado(ticket, 'cerrado', actor=solicitante)
        assert ticket.estado == 'cerrado'
        assert ticket.cerrado_en is not None
        
        # cerrado -> en_progreso (reopen by autor)
        cambiar_estado(ticket, 'en_progreso', actor=solicitante)
        assert ticket.estado == 'en_progreso'
        assert ticket.cerrado_en is None

    def test_invalid_transitions(self, setup_data):
        sector, solicitante, agente, directivo, ticket = setup_data
        
        # abierto -> resuelto (invalid, cannot skip en_progreso)
        with pytest.raises(ValidationError):
            cambiar_estado(ticket, 'resuelto', actor=agente)
            
        # abierto -> cerrado (invalid, cannot close from abierto)
        with pytest.raises(ValidationError):
            cambiar_estado(ticket, 'cerrado', actor=solicitante)

    def test_close_only_allowed_from_resuelto(self, setup_data):
        sector, solicitante, agente, directivo, ticket = setup_data
        
        # Current state is abierto
        with pytest.raises(ValidationError) as exc_info:
            cambiar_estado(ticket, 'cerrado', actor=solicitante)
        assert "Transición de estado inválida" in str(exc_info.value)
        
        # Transition to en_progreso
        cambiar_estado(ticket, 'en_progreso', actor=agente)
        with pytest.raises(ValidationError) as exc_info:
            cambiar_estado(ticket, 'cerrado', actor=solicitante)
        assert "Transición de estado inválida" in str(exc_info.value)

    def test_close_and_reopen_requires_authorized_actor(self, setup_data):
        sector, solicitante, agente, directivo, ticket = setup_data
        
        # Advance ticket to resuelto
        cambiar_estado(ticket, 'en_progreso', actor=agente)
        cambiar_estado(ticket, 'resuelto', actor=agente)
        
        # Another unrelated solicitante tries to close it
        other_solicitante = Usuario.objects.create(
            username='other@13dejulio.edu.ar', email='other@13dejulio.edu.ar',
            first_name='Otro', google_sub='sub-other', rol='solicitante'
        )
        
        with pytest.raises(ValidationError) as exc_info:
            cambiar_estado(ticket, 'cerrado', actor=other_solicitante)
        assert "Solo el autor o un gestor" in str(exc_info.value)
        
        # Correctly closed by agent (gestor)
        cambiar_estado(ticket, 'cerrado', actor=agente)
        assert ticket.estado == 'cerrado'
        
        # Unrelated user tries to reopen it
        with pytest.raises(ValidationError) as exc_info:
            cambiar_estado(ticket, 'en_progreso', actor=other_solicitante)
        assert "Solo el autor o un gestor" in str(exc_info.value)
