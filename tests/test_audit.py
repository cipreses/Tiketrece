import pytest
from sectores.models import Sector
from usuarios.models import Usuario
from tickets.models import Ticket, HistorialTicket
from tickets.services import crear_ticket, cambiar_estado, cambiar_prioridad, derivar_ticket, reasignar_sector

@pytest.mark.django_db
class TestAudit:

    @pytest.fixture
    def setup_data(self):
        sec_ti = Sector.objects.create(nombre='TI', descripcion='TI support', activo=True)
        sec_maint = Sector.objects.create(nombre='Mantenimiento', descripcion='Maint support', activo=True)
        
        sol = Usuario.objects.create(
            username='sol@13dejulio.edu.ar', email='sol@13dejulio.edu.ar',
            first_name='Solicitante', google_sub='sub-sol', rol='solicitante'
        )
        agent = Usuario.objects.create(
            username='agent@13dejulio.edu.ar', email='agent@13dejulio.edu.ar',
            first_name='Agente', google_sub='sub-agent', rol='agente'
        )
        agent.sectores.add(sec_ti)
        
        directivo = Usuario.objects.create(
            username='dir@13dejulio.edu.ar', email='dir@13dejulio.edu.ar',
            first_name='Directivo', google_sub='sub-dir', rol='directivo'
        )
        
        ticket = crear_ticket(
            autor=sol, sector=sec_ti, prioridad='media',
            titulo='Monitor parpadea', descripcion='Falla de video'
        )
        return sec_ti, sec_maint, sol, agent, directivo, ticket

    def test_audit_logs_created_on_state_change(self, setup_data):
        sec_ti, sec_maint, sol, agent, directivo, ticket = setup_data
        
        # Change state
        cambiar_estado(ticket, 'en_progreso', actor=agent)
        
        # Retrieve logs
        logs = HistorialTicket.objects.filter(ticket=ticket, tipo='estado')
        assert logs.count() == 1
        
        log = logs.first()
        assert log.actor == agent
        assert log.valor_anterior == 'abierto'
        assert log.valor_nuevo == 'en_progreso'

    def test_audit_logs_created_on_priority_change(self, setup_data):
        sec_ti, sec_maint, sol, agent, directivo, ticket = setup_data
        
        # Change priority
        cambiar_prioridad(ticket, 'alta', actor=agent)
        
        # Retrieve logs
        logs = HistorialTicket.objects.filter(ticket=ticket, tipo='prioridad')
        assert logs.count() == 1
        
        log = logs.first()
        assert log.actor == agent
        assert log.valor_anterior == 'media'
        assert log.valor_nuevo == 'alta'

    def test_audit_logs_created_on_derivation(self, setup_data):
        sec_ti, sec_maint, sol, agent, directivo, ticket = setup_data
        
        # Derive ticket
        derivar_ticket(ticket, sec_maint, actor=agent)
        
        # Retrieve logs
        logs = HistorialTicket.objects.filter(ticket=ticket, tipo='sector')
        assert logs.count() == 1
        
        log = logs.first()
        assert log.actor == agent
        assert log.valor_anterior == 'TI'
        assert log.valor_nuevo == 'Mantenimiento'

    def test_audit_logs_created_on_reasignation(self, setup_data):
        sec_ti, sec_maint, sol, agent, directivo, ticket = setup_data
        
        # Reassign ticket directivamente
        reasignar_sector(ticket, sec_maint, actor=directivo)
        
        # Retrieve logs
        logs = HistorialTicket.objects.filter(ticket=ticket, tipo='sector')
        assert logs.count() == 1
        
        log = logs.first()
        assert log.actor == directivo
        assert log.valor_anterior == 'TI'
        assert log.valor_nuevo == 'Mantenimiento'
