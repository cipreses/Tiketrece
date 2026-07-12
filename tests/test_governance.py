import pytest
from django.core.exceptions import ValidationError
from usuarios.models import Usuario, HistorialRol
from usuarios.services import cambiar_rol, cambiar_estado_activo

@pytest.mark.django_db
class TestGovernance:

    @pytest.fixture
    def setup_users(self):
        # Create a superadmin directivo
        superadmin = Usuario.objects.create(
            username='ti@13dejulio.edu.ar',
            email='ti@13dejulio.edu.ar',
            first_name='Super',
            google_sub='sub-super',
            rol='directivo',
            is_active=True
        )
        # Create a regular directivo
        directivo = Usuario.objects.create(
            username='dir1@13dejulio.edu.ar',
            email='dir1@13dejulio.edu.ar',
            first_name='Director',
            google_sub='sub-dir1',
            rol='directivo',
            is_active=True
        )
        # Create a solicitor
        solicitante = Usuario.objects.create(
            username='sol1@13dejulio.edu.ar',
            email='sol1@13dejulio.edu.ar',
            first_name='Solicitante',
            google_sub='sub-sol1',
            rol='solicitante',
            is_active=True
        )
        return superadmin, directivo, solicitante

    def test_superadmin_cannot_be_degraded_by_non_superadmin(self, setup_users):
        superadmin, directivo, solicitante = setup_users
        
        # A non-superadmin directivo attempts to degrade the superadmin
        with pytest.raises(ValidationError) as exc_info:
            cambiar_rol(superadmin, 'solicitante', actor=directivo)
        assert "no puede modificar el rol de un superadmin" in str(exc_info.value)
        
        # Verify role was not changed
        superadmin.refresh_from_db()
        assert superadmin.rol == 'directivo'

    def test_superadmin_can_be_degraded_by_another_superadmin(self, setup_users):
        superadmin, directivo, solicitante = setup_users
        
        # Set directivo as superadmin in settings list for override
        from django.test import override_settings
        with override_settings(SUPERADMIN_EMAILS=['ti@13dejulio.edu.ar', 'dir1@13dejulio.edu.ar']):
            # Now directivo is also a superadmin
            cambiar_rol(superadmin, 'solicitante', actor=directivo)
            superadmin.refresh_from_db()
            assert superadmin.rol == 'solicitante'

    def test_cannot_degrade_last_active_directivo(self, setup_users):
        superadmin, directivo, solicitante = setup_users
        
        # We deactivate 'directivo' so only 'superadmin' remains as the only active directivo
        cambiar_estado_activo(directivo, is_active=False, actor=superadmin)
        
        # Now try to degrade 'superadmin' (role change)
        with pytest.raises(ValidationError) as exc_info:
            cambiar_rol(superadmin, 'agente', actor=superadmin)
        assert "No se puede degradar al único directivo activo" in str(exc_info.value)

    def test_cannot_deactivate_last_active_directivo(self, setup_users):
        superadmin, directivo, solicitante = setup_users
        
        # We deactivate 'directivo'
        cambiar_estado_activo(directivo, is_active=False, actor=superadmin)
        
        # Now try to deactivate 'superadmin' (is_active change)
        with pytest.raises(ValidationError) as exc_info:
            cambiar_estado_activo(superadmin, is_active=False, actor=superadmin)
        assert "No se puede desactivar al único directivo activo" in str(exc_info.value)

    def test_role_change_creates_audit_log(self, setup_users):
        superadmin, directivo, solicitante = setup_users
        
        # Change role of solicitante to agent
        cambiar_rol(solicitante, 'agente', actor=directivo)
        
        # Verify log entry
        log = HistorialRol.objects.filter(usuario=solicitante).first()
        assert log is not None
        assert log.actor == directivo
        assert log.rol_anterior == 'solicitante'
        assert log.rol_nuevo == 'agente'
