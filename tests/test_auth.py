import pytest
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.test import override_settings
from unittest.mock import patch
from usuarios.auth_backend import GoogleOAuthBackend

@pytest.mark.django_db
class TestAuthentication:

    def test_mock_auth_inert_in_production(self):
        """
        Verify that if ENABLE_MOCK_AUTH is True but DEBUG is False,
        the backend raises ImproperlyConfigured, keeping it inert in production.
        """
        backend = GoogleOAuthBackend()
        with override_settings(ENABLE_MOCK_AUTH=True, DEBUG=False):
            # Attempting to authenticate via mock should trigger ImproperlyConfigured
            with pytest.raises(ImproperlyConfigured):
                backend.authenticate(None, mock_email="test@13dejulio.edu.ar", mock_name="Test")

    def test_mock_auth_rejects_non_domain_email(self):
        """
        Verify that even in mock mode, an email outside the @13dejulio.edu.ar
        domain is strictly rejected with a PermissionDenied exception.
        """
        backend = GoogleOAuthBackend()
        with override_settings(ENABLE_MOCK_AUTH=True, DEBUG=True):
            with pytest.raises(PermissionDenied) as exc_info:
                backend.authenticate(None, mock_email="test@gmail.com", mock_name="Test")
            assert "solo emite identidades de dominio @13dejulio.edu.ar" in str(exc_info.value)

    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_real_verification_exercises_and_rejects_non_domain(self, mock_verify):
        """
        Verify that passing a token exercises the real Google ID Token verification
        (which we mock to return a verified profile with a non-matching domain)
        and properly throws PermissionDenied.
        """
        # Set up mock payload for real verification returning a gmail email
        mock_verify.return_value = {
            'email': 'hacker@gmail.com',
            'email_verified': True,
            'iss': 'accounts.google.com',
            'aud': 'mock-client-id-for-development',
            'sub': 'google-sub-12345',
            'name': 'Hacker'
        }

        backend = GoogleOAuthBackend()
        # Enable mock auth to ensure that passing a token bypasses the mock branch
        # and goes to the real validation branch, which rejects it based on the domain.
        with override_settings(ENABLE_MOCK_AUTH=True, DEBUG=True, GOOGLE_CLIENT_ID='mock-client-id-for-development'):
            with pytest.raises(PermissionDenied) as exc_info:
                backend.authenticate(None, token="some-google-id-token")
            # The message comes from the real validation flow
            assert "Dominio del correo" in str(exc_info.value) or "Dominio alojado" in str(exc_info.value)

    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_real_verification_rejects_unverified_email(self, mock_verify):
        """
        Verify that the real verification flow rejects tokens where email_verified is False.
        """
        mock_verify.return_value = {
            'email': 'user@13dejulio.edu.ar',
            'email_verified': False, # unverified
            'iss': 'accounts.google.com',
            'aud': 'mock-client-id-for-development',
            'sub': 'google-sub-12345',
            'name': 'Unverified User'
        }

        backend = GoogleOAuthBackend()
        with override_settings(ENABLE_MOCK_AUTH=False, DEBUG=True, GOOGLE_CLIENT_ID='mock-client-id-for-development'):
            with pytest.raises(PermissionDenied) as exc_info:
                backend.authenticate(None, token="some-google-id-token")
            assert "no está verificado" in str(exc_info.value)

    def test_oauth_state_is_unique(self):
        """
        Verify that successive calls to google_login_redirect generate unique random state nonces.
        """
        from django.test import RequestFactory
        from django.contrib.sessions.middleware import SessionMiddleware
        from usuarios.views import google_login_redirect
        
        factory = RequestFactory()
        
        # Request 1
        request1 = factory.get('/auth/google/')
        middleware1 = SessionMiddleware(lambda req: None)
        middleware1.process_request(request1)
        request1.session.save()
        google_login_redirect(request1)
        state1 = request1.session.get('oauth_state')
        
        # Request 2
        request2 = factory.get('/auth/google/')
        middleware2 = SessionMiddleware(lambda req: None)
        middleware2.process_request(request2)
        request2.session.save()
        google_login_redirect(request2)
        state2 = request2.session.get('oauth_state')
        
        assert state1 is not None
        assert state2 is not None
        assert state1 != state2

    def test_oauth_callback_rejects_mismatched_state(self):
        """
        Verify that mismatched oauth_state throws PermissionDenied in callback.
        """
        from django.test import RequestFactory
        from django.contrib.sessions.middleware import SessionMiddleware
        from usuarios.views import google_login_callback
        
        factory = RequestFactory()
        request = factory.get('/auth/callback/?code=somecode&state=invalid_nonce')
        
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session['oauth_state'] = 'valid_nonce'
        request.session.save()
        
        with pytest.raises(PermissionDenied) as exc_info:
            google_login_callback(request)
        assert "Fallo en verificación CSRF de OAuth state" in str(exc_info.value)

    def test_audit_logs_are_readonly_at_db_level_update(self):
        """
        Verify that the PostgreSQL triggers block UPDATE operations on audit tables.
        """
        import django.db
        from tickets.models import Ticket, HistorialTicket
        from sectores.models import Sector
        from usuarios.models import Usuario
        
        sector = Sector.objects.create(nombre='Test Audit DB 1', activo=True)
        user = Usuario.objects.create(
            username='auditor1@13dejulio.edu.ar', email='auditor1@13dejulio.edu.ar', google_sub='sub-audit-db1'
        )
        ticket = Ticket.objects.create(autor=user, sector=sector, titulo='Test', descripcion='Desc')
        
        log = HistorialTicket.objects.create(
            ticket=ticket,
            actor=user,
            tipo='estado',
            valor_anterior='abierto',
            valor_nuevo='en_progreso'
        )
        
        # Attempting UPDATE must fail at database level
        log.valor_nuevo = 'resolved'
        with pytest.raises(django.db.utils.InternalError) as exc_info:
            log.save()
        assert "UPDATE and DELETE are prohibited" in str(exc_info.value)

    def test_audit_logs_are_readonly_at_db_level_delete(self):
        """
        Verify that the PostgreSQL triggers block DELETE operations on audit tables.
        """
        import django.db
        from tickets.models import Ticket, HistorialTicket
        from sectores.models import Sector
        from usuarios.models import Usuario
        
        sector = Sector.objects.create(nombre='Test Audit DB 2', activo=True)
        user = Usuario.objects.create(
            username='auditor2@13dejulio.edu.ar', email='auditor2@13dejulio.edu.ar', google_sub='sub-audit-db2'
        )
        ticket = Ticket.objects.create(autor=user, sector=sector, titulo='Test', descripcion='Desc')
        
        log = HistorialTicket.objects.create(
            ticket=ticket,
            actor=user,
            tipo='estado',
            valor_anterior='abierto',
            valor_nuevo='en_progreso'
        )
        
        # Attempting DELETE must fail at database level
        with pytest.raises(django.db.utils.InternalError) as exc_info:
            log.delete()
        assert "UPDATE and DELETE are prohibited" in str(exc_info.value)
