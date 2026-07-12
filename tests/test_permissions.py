import pytest
from django.core.exceptions import ValidationError
from sectores.models import Sector
from usuarios.models import Usuario
from tickets.models import Ticket
from tickets.permissions import obtener_tickets_visibles
from tickets.services import crear_ticket, cambiar_estado, cambiar_prioridad, derivar_ticket, reasignar_sector, agregar_comentario

@pytest.mark.django_db
class TestPermissions:

    @pytest.fixture
    def setup_data(self):
        # Create sectors
        sec1 = Sector.objects.create(nombre='TI', descripcion='TI support', activo=True)
        sec2 = Sector.objects.create(nombre='Regencia', descripcion='Pedagogía', activo=True)
        
        # Create users
        sol1 = Usuario.objects.create(
            username='sol1@13dejulio.edu.ar', email='sol1@13dejulio.edu.ar',
            first_name='Solicitante 1', google_sub='sub-sol1', rol='solicitante'
        )
        sol2 = Usuario.objects.create(
            username='sol2@13dejulio.edu.ar', email='sol2@13dejulio.edu.ar',
            first_name='Solicitante 2', google_sub='sub-sol2', rol='solicitante'
        )
        
        agent_ti = Usuario.objects.create(
            username='agent1@13dejulio.edu.ar', email='agent1@13dejulio.edu.ar',
            first_name='Agente TI', google_sub='sub-agent1', rol='agente'
        )
        agent_ti.sectores.add(sec1)
        
        directivo = Usuario.objects.create(
            username='dir@13dejulio.edu.ar', email='dir@13dejulio.edu.ar',
            first_name='Directivo', google_sub='sub-dir', rol='directivo'
        )
        
        # Create tickets
        ticket_ti = crear_ticket(
            autor=sol1, sector=sec1, prioridad='media',
            titulo='PC rota', descripcion='No enciende la PC'
        )
        ticket_reg = crear_ticket(
            autor=sol2, sector=sec2, prioridad='baja',
            titulo='Firma de actas', descripcion='Planillas de notas'
        )
        
        return sec1, sec2, sol1, sol2, agent_ti, directivo, ticket_ti, ticket_reg

    def test_scope_visibility_filter(self, setup_data):
        sec1, sec2, sol1, sol2, agent_ti, directivo, ticket_ti, ticket_reg = setup_data
        
        # Solicitante 1 should only see ticket_ti (since they created it)
        visibles_sol1 = obtener_tickets_visibles(sol1)
        assert visibles_sol1.count() == 1
        assert ticket_ti in visibles_sol1
        assert ticket_reg not in visibles_sol1
        
        # Agent TI should only see ticket_ti (belongs to TI sector)
        visibles_agent = obtener_tickets_visibles(agent_ti)
        assert visibles_agent.count() == 1
        assert ticket_ti in visibles_agent
        assert ticket_reg not in visibles_agent
        
        # Directivo should see all tickets
        visibles_dir = obtener_tickets_visibles(directivo)
        assert visibles_dir.count() == 2
        assert ticket_ti in visibles_dir
        assert ticket_reg in visibles_dir

    def test_agent_cannot_modify_unrelated_tickets(self, setup_data):
        sec1, sec2, sol1, sol2, agent_ti, directivo, ticket_ti, ticket_reg = setup_data
        
        # Agent TI tries to change status of ticket_reg (Regencia sector)
        with pytest.raises(ValidationError) as exc_info:
            cambiar_estado(ticket_reg, 'en_progreso', actor=agent_ti)
        assert "Un agente solo puede modificar tickets de sus sectores" in str(exc_info.value)
        
        # Agent TI tries to change priority of ticket_reg
        with pytest.raises(ValidationError) as exc_info:
            cambiar_prioridad(ticket_reg, 'urgente', actor=agent_ti)
        assert "Un agente solo puede cambiar la prioridad" in str(exc_info.value)
        
        # Agent TI tries to derive ticket_reg
        with pytest.raises(ValidationError) as exc_info:
            derivar_ticket(ticket_reg, sec1, actor=agent_ti)
        assert "Un agente solo puede derivar tickets de sus propios sectores" in str(exc_info.value)

    def test_directivo_global_actions_allowed(self, setup_data):
        sec1, sec2, sol1, sol2, agent_ti, directivo, ticket_ti, ticket_reg = setup_data
        
        # Directivo can change priority of any ticket
        cambiar_prioridad(ticket_reg, 'alta', actor=directivo)
        ticket_reg.refresh_from_db()
        assert ticket_reg.prioridad == 'alta'
        
        # Directivo can reassign sector of any ticket (RF-08)
        reasignar_sector(ticket_reg, sec1, actor=directivo)
        ticket_reg.refresh_from_db()
        assert ticket_reg.sector == sec1

    def test_comentar_related_rule(self, setup_data):
        sec1, sec2, sol1, sol2, agent_ti, directivo, ticket_ti, ticket_reg = setup_data
        
        # Solicitante 1 comments on their own ticket (PC rota) -> allowed
        agregar_comentario(ticket_ti, autor=sol1, texto="Por favor, es urgente.")
        assert ticket_ti.comentarios.filter(autor=sol1).exists()
        
        # Solicitante 1 comments on Solicitante 2's ticket -> rejected
        with pytest.raises(ValidationError) as exc_info:
            agregar_comentario(ticket_reg, autor=sol1, texto="Comentario metido.")
        assert "No tienes permisos para comentar" in str(exc_info.value)
        
        # Agent TI comments on Regencia ticket -> rejected
        with pytest.raises(ValidationError) as exc_info:
            agregar_comentario(ticket_reg, autor=agent_ti, texto="Comentario del agente.")
        assert "No tienes permisos para comentar" in str(exc_info.value)
        
        # Directivo comments on any ticket -> allowed
        agregar_comentario(ticket_reg, autor=directivo, texto="Revisando administrativamente.")
        assert ticket_reg.comentarios.filter(autor=directivo).exists()
