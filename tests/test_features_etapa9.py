import pytest
import os
import csv
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from tickets.models import Ticket, HistorialTicket
from sectores.models import Sector
from tickets.permissions import puede_cambiar_estado

Usuario = get_user_model()

@pytest.fixture
def init_data():
    # Create sectors
    sec_ti = Sector.objects.create(nombre="TI", activo=True)
    sec_maint = Sector.objects.create(nombre="Mantenimiento", activo=True)
    
    # Create users
    dir_user = Usuario.objects.create(
        username="directivo@13dejulio.edu.ar",
        email="directivo@13dejulio.edu.ar",
        google_sub="sub-directivo",
        rol="directivo"
    )
    agent_user = Usuario.objects.create(
        username="agente@13dejulio.edu.ar",
        email="agente@13dejulio.edu.ar",
        google_sub="sub-agente",
        rol="agente"
    )
    # Link agent to TI sector
    agent_user.sectores.add(sec_ti)
    
    solic1 = Usuario.objects.create(
        username="solic1@13dejulio.edu.ar",
        email="solic1@13dejulio.edu.ar",
        google_sub="sub-solic1",
        rol="solicitante"
    )
    solic2 = Usuario.objects.create(
        username="solic2@13dejulio.edu.ar",
        email="solic2@13dejulio.edu.ar",
        google_sub="sub-solic2",
        rol="solicitante"
    )
    
    return {
        'sec_ti': sec_ti,
        'sec_maint': sec_maint,
        'dir_user': dir_user,
        'agent_user': agent_user,
        'solic1': solic1,
        'solic2': solic2
    }

@pytest.mark.django_db
class TestTextSearch:
    
    def test_search_matches_and_excludes(self, init_data):
        """
        Verify that searching returns matching tickets and excludes non-matching ones.
        """
        # Create tickets
        t1 = Ticket.objects.create(
            autor=init_data['solic1'],
            sector=init_data['sec_ti'],
            titulo="Proyector roto en aula 10",
            descripcion="El proyector no enciende"
        )
        t2 = Ticket.objects.create(
            autor=init_data['solic1'],
            sector=init_data['sec_ti'],
            titulo="Sin internet en dirección",
            descripcion="La red wifi TI-Red está caída"
        )
        
        # Test search matching title
        qs = Ticket.objects.all()
        
        # Search for "proyector"
        res = qs.filter(titulo__icontains="proyector") | qs.filter(descripcion__icontains="proyector")
        assert t1 in res
        assert t2 not in res
        
        # Search for "wifi"
        res2 = qs.filter(titulo__icontains="wifi") | qs.filter(descripcion__icontains="wifi")
        assert t2 in res2
        assert t1 not in res2

    def test_search_never_violates_scope(self, init_data, client):
        """
        Verify that text search is strictly restricted to user's visual scope.
        A solicitante searching for "proyector" should not see another solicitante's ticket.
        """
        # solic1 ticket matching "proyector"
        t1 = Ticket.objects.create(
            autor=init_data['solic1'],
            sector=init_data['sec_ti'],
            titulo="Proyector roto aula 3",
            descripcion="Falla enchufe"
        )
        # solic2 ticket matching "proyector"
        t2 = Ticket.objects.create(
            autor=init_data['solic2'],
            sector=init_data['sec_ti'],
            titulo="Proyector aula 5",
            descripcion="Falta control remoto"
        )
        
        # Login as solic1
        client.force_login(init_data['solic1'])
        
        # Request list view with search term "proyector"
        response = client.get(reverse('tickets_list') + '?q=proyector')
        assert response.status_code == 200
        
        # solic1 must see only t1, never t2 (since t2 belongs to solic2)
        tickets_in_context = response.context['tickets']
        assert t1 in tickets_in_context
        assert t2 not in tickets_in_context


@pytest.mark.django_db
class TestCSVExport:
    
    def test_export_respects_scope_and_filters(self, init_data, client):
        """
        Verify CSV export streams tickets limited to the user's scope and applied filters.
        """
        # solic1 tickets
        t1 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI", estado="abierto"
        )
        t2 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket Mantenimiento", estado="resuelto"
        )
        # solic2 ticket
        t3 = Ticket.objects.create(
            autor=init_data['solic2'], sector=init_data['sec_ti'], titulo="Otro Ticket", estado="abierto"
        )
        
        # Login as solic1
        client.force_login(init_data['solic1'])
        
        # Request export
        response = client.get(reverse('export_tickets_csv'))
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/csv; charset=utf-8'
        
        # Parse streaming content
        content = b"".join(response.streaming_content).decode('utf-8')
        
        # Check UTF-8 BOM
        assert content.startswith('\ufeff')
        
        # Read rows
        reader = csv.reader(content.lstrip('\ufeff').splitlines())
        rows = list(reader)
        
        # Row 1 is header
        assert rows[0] == ['id', 'titulo', 'sector', 'autor_email', 'prioridad', 'estado', 'creado_en', 'actualizado_en', 'cerrado_en']
        
        # Other rows should only contain solic1 tickets (t1 and t2), not solic2 (t3)
        ticket_ids = [int(row[0]) for row in rows[1:]]
        assert t1.id in ticket_ids
        assert t2.id in ticket_ids
        assert t3.id not in ticket_ids

    def test_export_bypass_by_query_param_is_blocked(self, init_data, client):
        """
        Verify that if a solicitante tries to bypass scope by manually editing query params
        (e.g., searching for author=solic2), they do not receive other users' tickets in the CSV export.
        """
        t1 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        t2 = Ticket.objects.create(
            autor=init_data['solic2'], sector=init_data['sec_ti'], titulo="Otro Ticket"
        )
        
        # Login as solic1
        client.force_login(init_data['solic1'])
        
        # Attempt bypass by querying autor=solic2@13dejulio.edu.ar
        response = client.get(reverse('export_tickets_csv') + '?autor=solic2@13dejulio.edu.ar')
        assert response.status_code == 200
        
        content = b"".join(response.streaming_content).decode('utf-8')
        reader = csv.reader(content.lstrip('\ufeff').splitlines())
        rows = list(reader)
        
        ticket_ids = [int(row[0]) for row in rows[1:]]
        # Should not contain any tickets because solic2's tickets are out of solic1's scope
        # and solic1's own tickets are filtered out by the ?autor=solic2 parameter.
        assert len(ticket_ids) == 0

    def test_export_formula_injection_defense(self, init_data, client):
        """
        Verify that text fields starting with dangerous formula characters (=, +, -, @, tab, cr)
        are prepended with a single quote (') to neutralize CSV Injection.
        """
        # Ticket with formula titles
        t1 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="=1+1"
        )
        t2 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="+SUM(A1:A5)"
        )
        t3 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Normal Title"
        )
        
        client.force_login(init_data['solic1'])
        
        response = client.get(reverse('export_tickets_csv'))
        content = b"".join(response.streaming_content).decode('utf-8')
        reader = csv.reader(content.lstrip('\ufeff').splitlines())
        rows = list(reader)
        
        # Map row title by ticket id
        title_map = {int(row[0]): row[1] for row in rows[1:]}
        
        # Formula titles must have the leading apostrophe
        assert title_map[t1.id] == "'=1+1"
        assert title_map[t2.id] == "'+SUM(A1:A5)"
        
        # Normal title should remain untouched
        assert title_map[t3.id] == "Normal Title"


@pytest.mark.django_db
class TestUISmokeAndPermissions:
    
    def test_directivo_views_detail_controls(self, init_data, client):
        """
        Verify that rendering ticket detail logged in as DIRECTIVO displays the
        'cambiar prioridad' and 'reasignar sector' controls.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Test Ticket"
        )
        
        client.force_login(init_data['dir_user'])
        response = client.get(reverse('ticket_detail', args=[ticket.id]))
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        # Check controls
        assert "Modificar Prioridad:" in html
        assert "Reasignar Sector (Global):" in html

    def test_list_contains_search_and_export_controls(self, init_data, client):
        """
        Verify that the ticket list page renders the text search input and the export link.
        """
        client.force_login(init_data['dir_user'])
        response = client.get(reverse('tickets_list'))
        assert response.status_code == 200
        
        html = response.content.decode('utf-8')
        assert 'name="q"' in html
        assert 'tickets/export/' in html
        assert "Exportar CSV" in html

    def test_author_status_change_permission_alignment(self, init_data):
        """
        Verify that a solicitante author can only transition status when the ticket
        is in 'resuelto' or 'cerrado' states, and is restricted in other states.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Test Ticket", estado="abierto"
        )
        
        # Estado: abierto -> Author cannot change state (return False)
        assert puede_cambiar_estado(init_data['solic1'], ticket) is False
        
        # Estado: resuelto -> Author can close it (return True)
        ticket.estado = 'resuelto'
        assert puede_cambiar_estado(init_data['solic1'], ticket) is True
        
        # Estado: cerrado -> Author can reopen it (return True)
        ticket.estado = 'cerrado'
        assert puede_cambiar_estado(init_data['solic1'], ticket) is True


@pytest.mark.django_db
class TestNotifications:

    def test_notification_creation_and_actor_exclusion(self, init_data):
        """
        Verify that notifications are created for the correct active recipients (author + sector agents)
        and that the actor who performs the change is excluded (no self-notification).
        """
        from tickets.models import Notificacion
        from tickets.services import cambiar_prioridad
        
        # Create a ticket owned by solic1
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Test Notif", prioridad="baja"
        )
        
        # Action performed by agent_user (who belongs to sec_ti)
        # Author: solic1, Agent: agent_user
        # Expect notification created only for solic1 (since agent_user is actor)
        cambiar_prioridad(ticket, "alta", init_data['agent_user'])
        
        notifs = Notificacion.objects.all()
        assert notifs.count() == 1
        assert notifs[0].destinatario == init_data['solic1']
        assert notifs[0].tipo == 'prioridad'
        
        # Action performed by solic1 (author)
        # Expect notification created only for agent_user (since solic1 is actor)
        from tickets.services import agregar_comentario
        agregar_comentario(ticket, init_data['solic1'], "Hola agentes!")
        
        # Total notifications should now be 2
        notifs = Notificacion.objects.all()
        assert notifs.count() == 2
        
        # The latest notification must be for the agent_user
        latest_notif = Notificacion.objects.filter(tipo='comentario').first()
        assert latest_notif is not None
        assert latest_notif.destinatario == init_data['agent_user']

    def test_derivation_notifies_both_sectors_agents(self, init_data):
        """
        Verify that derivation/reasignation notifies agents of both the origin and destination sectors
        plus the author, while excluding the actor.
        """
        from tickets.models import Notificacion
        from tickets.services import derivar_ticket
        
        # Create another agent for maint sector
        maint_agent = Usuario.objects.create(
            username="maint@13dejulio.edu.ar",
            email="maint@13dejulio.edu.ar",
            google_sub="sub-maint-agent",
            rol="agente"
        )
        maint_agent.sectores.add(init_data['sec_maint'])
        
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Test Deriv"
        )
        
        # Derivation performed by dir_user (who belongs to no sector)
        # Recipients expected: author (solic1) + origin agents (agent_user) + destination agents (maint_agent)
        # Excluding actor (dir_user)
        derivar_ticket(ticket, init_data['sec_maint'], init_data['dir_user'])
        
        notifs = Notificacion.objects.all()
        # 3 notifications should be created
        assert notifs.count() == 3
        
        destinatarios = [n.destinatario for n in notifs]
        assert init_data['solic1'] in destinatarios
        assert init_data['agent_user'] in destinatarios
        assert maint_agent in destinatarios
        assert init_data['dir_user'] not in destinatarios

    def test_unrelated_agent_does_not_receive_notification(self, init_data):
        """
        Verify that an agent from an unrelated sector does NOT receive notifications.
        """
        from tickets.models import Notificacion
        from tickets.services import cambiar_prioridad
        
        # Create a ticket in Maintenance sector
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_maint'], titulo="Maint Ticket"
        )
        
        # agent_user belongs to TI sector (unrelated)
        # Action performed by dir_user
        # Expect notification only for solic1 (author). agent_user should not get one.
        cambiar_prioridad(ticket, "alta", init_data['dir_user'])
        
        notifs = Notificacion.objects.filter(destinatario=init_data['agent_user'])
        assert notifs.count() == 0

    def test_notifications_scope_and_unread_count(self, init_data, client):
        """
        Verify that a user only sees/counts their own notifications.
        """
        from tickets.models import Notificacion
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Test"
        )
        # Create 2 unread notifications for solic1
        Notificacion.objects.create(destinatario=init_data['solic1'], ticket=ticket, tipo="estado", mensaje="Msg 1")
        Notificacion.objects.create(destinatario=init_data['solic1'], ticket=ticket, tipo="estado", mensaje="Msg 2")
        
        # Create 1 unread notification for solic2
        Notificacion.objects.create(destinatario=init_data['solic2'], ticket=ticket, tipo="estado", mensaje="Msg 3")
        
        # Login as solic1
        client.force_login(init_data['solic1'])
        response = client.get(reverse('notificaciones_dropdown'))
        assert response.status_code == 200
        
        # solic1 should only count 2 unread notifications
        assert response.context['unread_count'] == 2
        notifs_in_context = response.context['notificaciones']
        assert notifs_in_context.count() == 2
        for n in notifs_in_context:
            assert n.destinatario == init_data['solic1']

    def test_idor_prevented_on_mark_as_read(self, init_data, client):
        """
        Verify that a user cannot mark another user's notification as read (returns 404).
        """
        from tickets.models import Notificacion
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Test"
        )
        
        # Notification owned by solic2
        notif = Notificacion.objects.create(
            destinatario=init_data['solic2'], ticket=ticket, tipo="estado", mensaje="Msg"
        )
        
        # Login as solic1
        client.force_login(init_data['solic1'])
        
        # Attempt to mark solic2's notification as read
        response = client.post(reverse('marcar_leida_notificacion', args=[notif.id]))
        assert response.status_code == 404
        
        # Confirm it remains unread in database
        notif.refresh_from_db()
        assert notif.leida is False


from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.mark.django_db
class TestAttachments:

    @pytest.fixture(autouse=True)
    def temp_media(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        settings.MEDIA_URL = '/media/'

    def test_attachment_upload_permission_scope(self, init_data, client):
        """
        Verify that a related user can upload files but an unrelated user is blocked (403).
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        # Valid PNG file content
        valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        png_file = SimpleUploadedFile("test.png", valid_png, content_type="image/png")
        
        # Unrelated user (solic2) attempts to upload to solic1's ticket
        client.force_login(init_data['solic2'])
        response = client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': png_file})
        assert response.status_code == 403
        assert ticket.adjuntos.count() == 0
        
        # Related user (solic1 - author) uploads to their own ticket
        png_file.seek(0)
        client.force_login(init_data['solic1'])
        response2 = client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': png_file})
        assert response2.status_code == 302 # Redirects on success
        assert ticket.adjuntos.count() == 1

    def test_file_format_and_magic_bytes_validation(self, init_data, client):
        """
        Verify that files not matching whitelisted formats or with mismatched magic bytes are rejected.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        client.force_login(init_data['solic1'])
        
        # 1. Reject SVG file (XSS prevention)
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        svg_file = SimpleUploadedFile("xss.svg", svg_content, content_type="image/svg+xml")
        client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': svg_file})
        assert ticket.adjuntos.count() == 0 # Blocked
        
        # 2. Reject mismatched magic bytes (HTML disguised as PNG)
        fake_png = b'<html><body>Fake PNG</body></html>'
        fake_png_file = SimpleUploadedFile("disguised.png", fake_png, content_type="image/png")
        client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': fake_png_file})
        assert ticket.adjuntos.count() == 0 # Blocked
        
        # 3. Reject forbidden extension even if magic bytes match (.exe extension)
        valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        malicious_exe = SimpleUploadedFile("malware.exe", valid_png, content_type="image/png")
        client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': malicious_exe})
        assert ticket.adjuntos.count() == 0 # Blocked

    def test_file_size_exceeded_rejection(self, init_data, client):
        """
        Verify that files exceeding the 10 MB limit are rejected.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        client.force_login(init_data['solic1'])
        
        # Create a large dummy file > 10 MB with valid PDF header
        large_content = b'%PDF-1.4\n' + b'0' * (10 * 1024 * 1024 + 100)
        large_file = SimpleUploadedFile("large.pdf", large_content, content_type="application/pdf")
        
        client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': large_file})
        assert ticket.adjuntos.count() == 0 # Blocked

    def test_secure_download_and_idor_block(self, init_data, client):
        """
        Verify secure download: requires login, enforces scope (IDOR block), returns nosniff,
        and uses attachment disposition. Also test direct /media/ path returns 404.
        """
        from tickets.models import Adjunto
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        png_file = SimpleUploadedFile("safe.png", valid_png, content_type="image/png")
        
        # Upload
        client.force_login(init_data['solic1'])
        client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': png_file})
        adjunto = ticket.adjuntos.first()
        assert adjunto is not None
        
        # 1. Unrelated user (solic2) attempts to download
        client.force_login(init_data['solic2'])
        response = client.get(reverse('descargar_adjunto', args=[adjunto.id]))
        assert response.status_code == 403
        
        # 2. Author (solic1) downloads (happy path check)
        client.force_login(init_data['solic1'])
        response2 = client.get(reverse('descargar_adjunto', args=[adjunto.id]))
        assert response2.status_code == 200
        
        # Compare bytes: happy path byte-by-byte check
        downloaded_bytes = b"".join(response2.streaming_content)
        assert downloaded_bytes == valid_png
        
        # Verify headers
        assert response2['X-Content-Type-Options'] == 'nosniff'
        assert response2['Content-Type'] == 'image/png'
        assert 'attachment;' in response2['Content-Disposition']
        assert 'filename="safe.png"' in response2['Content-Disposition']
        
        # 3. Direct MEDIA_URL access check (must return 404)
        direct_url = f"/media/{adjunto.archivo.name}"
        response3 = client.get(direct_url)
        assert response3.status_code == 404

    def test_path_traversal_neutralization(self, init_data, client):
        """
        Verify that attempts at path traversal via filenames are neutralized (UUID saved file).
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        traversal_file = SimpleUploadedFile("../../../evil.png", valid_png, content_type="image/png")
        
        client.force_login(init_data['solic1'])
        client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': traversal_file})
        
        adjunto = ticket.adjuntos.first()
        assert adjunto is not None
        assert ".." not in adjunto.nombre_original
        
        # Path on disk should be inside the tickets directory under a safe UUID
        filename = os.path.basename(adjunto.archivo.name)
        assert ".." not in adjunto.archivo.name
        assert filename != "evil.png"
        assert len(filename) >= 36 # UUID4 length is 36


