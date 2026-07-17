from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from usuarios.models import Usuario

class GoogleOAuthBackend(BaseBackend):
    def authenticate(self, request, token=None, mock_email=None, mock_name=None, mock_sub=None, **kwargs):
        """
        Authenticates a user via Google OAuth 2.0 ID Token or a Mock token for local development.
        """
        # 1. Mock Authentication check for development and tests
        if getattr(settings, 'ENABLE_MOCK_AUTH', False):
            # Double check: raise if ENABLE_MOCK_AUTH is enabled in production
            if not settings.DEBUG:
                raise ImproperlyConfigured("CRITICAL SECURITY ERROR: ENABLE_MOCK_AUTH is True in production!")
            
            if mock_email:
                # Blindage requirement: mock only emits @13dejulio.edu.ar identities
                domain = mock_email.split('@')[-1] if mock_email else ''
                if domain.lower() != '13dejulio.edu.ar':
                    raise PermissionDenied("El mock de inicio de sesión solo emite identidades de dominio @13dejulio.edu.ar.")
                
                sub = mock_sub or f"mock-sub-{mock_email}"
                name = mock_name or mock_email.split('@')[0].capitalize()
                return self._get_or_create_user(sub, mock_email, name)

        # 2. Real Google OAuth ID Token Verification
        if token:
            try:
                # Verifies signature, aud (client id), iss (issuer), and expiration
                idinfo = id_token.verify_oauth2_token(
                    token,
                    google_requests.Request(),
                    settings.GOOGLE_CLIENT_ID
                )
                
                # Rule 6: explicit check for email_verified == True
                if not idinfo.get('email_verified', False):
                    raise PermissionDenied("El correo electrónico de Google no está verificado.")
                
                # Check issuer explicitly
                iss = idinfo.get('iss', '')
                if iss not in ['accounts.google.com', 'https://accounts.google.com']:
                    raise PermissionDenied(f"Emisor de token (iss) '{iss}' no válido.")
                
                # Check domain restriction: prefer 'hd' claim, fall back to email suffix
                email = idinfo.get('email', '')
                hd = idinfo.get('hd', '')
                domain_allowed = '13dejulio.edu.ar'
                
                if hd:
                    if hd.lower() != domain_allowed:
                        raise PermissionDenied(f"Dominio alojado (hd) '{hd}' no permitido.")
                else:
                    domain = email.split('@')[-1] if email else ''
                    if domain.lower() != domain_allowed:
                        raise PermissionDenied(f"Dominio del correo '{domain}' no permitido.")
                
                sub = idinfo.get('sub')
                name = idinfo.get('name', email.split('@')[0].capitalize())
                
                return self._get_or_create_user(sub, email, name)
                
            except PermissionDenied:
                # Propagate specific permission errors
                raise
            except Exception as e:
                # Fail-safe wrap other validation exceptions
                raise PermissionDenied(f"Verificación de token de Google fallida: {str(e)}")

        return None

    def _get_or_create_user(self, sub, email, name):
        """
        Creates or updates a local user based on the verified google_sub.
        """
        try:
            user = Usuario.objects.get(google_sub=sub)
            # Sync user details if changed
            if user.email != email or user.first_name != name:
                user.email = email
                user.first_name = name
                user.save()
            return user
        except Usuario.DoesNotExist:
            is_super = email in getattr(settings, 'SUPERADMIN_EMAILS', [])
            rol = 'directivo' if is_super else 'solicitante'
            estado_aprobacion = 'aprobado' if is_super else 'pendiente'
            
            user = Usuario.objects.create(
                username=email,
                email=email,
                first_name=name,
                google_sub=sub,
                rol=rol,
                estado_aprobacion=estado_aprobacion,
                is_active=True,
                _keep_pending_in_tests=True
            )
            # password will be initialized as unusable in Usuario.save()
            return user

    def get_user(self, user_id):
        try:
            return Usuario.objects.get(pk=user_id)
        except Usuario.DoesNotExist:
            return None
