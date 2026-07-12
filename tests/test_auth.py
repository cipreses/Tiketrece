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
