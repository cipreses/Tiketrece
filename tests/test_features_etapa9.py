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

    def test_uploaded_attachment_saved_under_media_root(self, init_data, client, settings):
        """
        Verify that an uploaded attachment is physically saved inside the MEDIA_ROOT folder,
        not in the project root or elsewhere.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        png_file = SimpleUploadedFile("safe.png", valid_png, content_type="image/png")
        
        client.force_login(init_data['solic1'])
        client.post(reverse('subir_adjunto', args=[ticket.id]), {'archivo': png_file})
        
        adjunto = ticket.adjuntos.first()
        assert adjunto is not None
        
        # Get the absolute path on disk using the file field path property
        file_path_on_disk = adjunto.archivo.path
        
        # Verify it starts with settings.MEDIA_ROOT
        assert file_path_on_disk.startswith(settings.MEDIA_ROOT)
        
        # Verify the file actually exists on the filesystem in that location
        assert os.path.exists(file_path_on_disk)

    def test_create_ticket_with_multiple_valid_attachments(self, init_data, client, settings):
        """
        Verify that creating a ticket with multiple valid attachments creates the ticket
        and all attachments, and stores them under MEDIA_ROOT.
        """
        valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        valid_pdf = b'%PDF-1.4\n%EOF'
        
        file1 = SimpleUploadedFile("pic.png", valid_png, content_type="image/png")
        file2 = SimpleUploadedFile("doc.pdf", valid_pdf, content_type="application/pdf")
        
        client.force_login(init_data['solic1'])
        
        post_data = {
            'sector_id': init_data['sec_ti'].id,
            'prioridad': 'media',
            'titulo': 'Ticket con archivos',
            'descripcion': 'Falla reportada con capturas',
            'archivos': [file1, file2]
        }
        
        response = client.post(reverse('crear_ticket'), post_data)
        assert response.status_code == 302 # Redirect on success
        
        # Verify ticket and attachments were created
        ticket = Ticket.objects.get(titulo='Ticket con archivos')
        assert ticket.adjuntos.count() == 2
        
        for adj in ticket.adjuntos.all():
            assert adj.subido_por == init_data['solic1']
            assert adj.archivo.path.startswith(settings.MEDIA_ROOT)
            assert os.path.exists(adj.archivo.path)

    def test_create_ticket_with_invalid_attachment_rolls_back_everything(self, init_data, client):
        """
        Verify that if any of the attached files is invalid, no ticket is created
        and no attachments are saved in database (atomic rollback).
        """
        valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        fake_png = b'<html>Fake</html>' # Mismatched magic bytes
        
        file1 = SimpleUploadedFile("ok.png", valid_png, content_type="image/png")
        file2 = SimpleUploadedFile("fake.png", fake_png, content_type="image/png")
        
        client.force_login(init_data['solic1'])
        
        tickets_count_before = Ticket.objects.count()
        
        post_data = {
            'sector_id': init_data['sec_ti'].id,
            'prioridad': 'media',
            'titulo': 'Ticket Fallido',
            'descripcion': 'Falla atómica',
            'archivos': [file1, file2]
        }
        
        response = client.post(reverse('crear_ticket'), post_data)
        assert response.status_code == 200 # Re-renders page on error
        
        # Verify no new tickets were created
        assert Ticket.objects.count() == tickets_count_before
        
        # Confirm no attachments exist for 'Ticket Fallido'
        from tickets.models import Adjunto
        assert Adjunto.objects.filter(nombre_original="ok.png").count() == 0

    def test_create_ticket_without_attachments_succeeds(self, init_data, client):
        """
        Verify that creating a ticket without files is optional and succeeds.
        """
        client.force_login(init_data['solic1'])
        
        post_data = {
            'sector_id': init_data['sec_ti'].id,
            'prioridad': 'media',
            'titulo': 'Ticket limpio',
            'descripcion': 'Sin adjuntos'
        }
        
        response = client.post(reverse('crear_ticket'), post_data)
        assert response.status_code == 302
        
        ticket = Ticket.objects.get(titulo='Ticket limpio')
        assert ticket.adjuntos.count() == 0

    def test_create_ticket_exceeds_max_files_limit(self, init_data, client):
        """
        Verify that attempting to attach more than 5 files blocks ticket creation.
        """
        valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        files = [
            SimpleUploadedFile(f"file{i}.png", valid_png, content_type="image/png")
            for i in range(6)
        ]
        
        client.force_login(init_data['solic1'])
        tickets_count_before = Ticket.objects.count()
        
        post_data = {
            'sector_id': init_data['sec_ti'].id,
            'prioridad': 'media',
            'titulo': 'Ticket saturado',
            'descripcion': 'Demasiados adjuntos',
            'archivos': files
        }
        
        response = client.post(reverse('crear_ticket'), post_data)
        assert response.status_code == 200 # Re-renders creating page
        
        # Verify ticket was blocked
        assert Ticket.objects.count() == tickets_count_before


from unittest.mock import patch
from django.core import mail

@pytest.mark.django_db(transaction=True)
class TestEmailNotifications:
    def test_email_notifications_sent_on_action(self, init_data, client, django_capture_on_commit_callbacks):
        """
        Verify that email notifications are sent to the correct active users
        excluding the actor performing the change.
        """
        # Create a ticket
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        # Create another agent in the same sector
        agent2 = Usuario.objects.create(
            username="agent2@13dejulio.edu.ar",
            email="agent2@13dejulio.edu.ar",
            google_sub="sub-agent2",
            rol="agente"
        )
        agent2.sectores.add(init_data['sec_ti'])
        
        # Clear outbox
        mail.outbox = []
        
        # Login as the agent_user (actor) to add a comment
        client.force_login(init_data['agent_user'])
        
        with django_capture_on_commit_callbacks(execute=True):
            client.post(reverse('agregar_comentario', args=[ticket.id]), {'texto': "Comentario del agente"})
            
        # Verify emails sent to solic1 (author) and agent2 (other agent in sector)
        # It should not send to agent_user (actor)
        assert len(mail.outbox) == 2
        recipients = [email.to[0] for email in mail.outbox]
        assert init_data['solic1'].email in recipients
        assert agent2.email in recipients
        assert init_data['agent_user'].email not in recipients
        
        # Verify content
        for email in mail.outbox:
            assert "[Tiketrece] Ticket #" in email.subject
            assert "Nuevo comentario de agente@13dejulio.edu.ar" in email.body
            assert "/tickets/" in email.body

    def test_email_notifications_respects_opt_out(self, init_data, client, django_capture_on_commit_callbacks):
        """
        Verify that a user with recibir_emails=False does not receive email notifications
        but still receives in-app notifications.
        """
        # Opt-out solic1
        solic = init_data['solic1']
        solic.recibir_emails = False
        solic.save()
        
        ticket = Ticket.objects.create(
            autor=solic, sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        mail.outbox = []
        client.force_login(init_data['agent_user'])
        
        with django_capture_on_commit_callbacks(execute=True):
            client.post(reverse('agregar_comentario', args=[ticket.id]), {'texto': "Comentario del agente"})
            
        # Outbox should be empty (solic1 opted out, agent_user is actor)
        assert len(mail.outbox) == 0
        
        # But in-app notification must exist
        assert ticket.notificaciones.filter(destinatario=solic).exists()

    def test_email_notifications_not_sent_to_unrelated_users(self, init_data, client, django_capture_on_commit_callbacks):
        """
        Verify that email notifications are not sent to unrelated users.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        # Create an unrelated agent in Mantenimiento sector
        maint_agent = Usuario.objects.create(
            username="maint@13dejulio.edu.ar",
            email="maint@13dejulio.edu.ar",
            google_sub="sub-maint",
            rol="agente"
        )
        maint_agent.sectores.add(init_data['sec_maint'])
        
        mail.outbox = []
        client.force_login(init_data['solic1'])
        
        with django_capture_on_commit_callbacks(execute=True):
            client.post(reverse('agregar_comentario', args=[ticket.id]), {'texto': "Actualizado"})
            
        # Verify email is not sent to unrelated maint_agent
        for email in mail.outbox:
            assert maint_agent.email not in email.to

    @patch('tickets.services.send_mail')
    def test_email_notifications_error_isolation(self, mock_send_mail, init_data, client, django_capture_on_commit_callbacks):
        """
        Verify that if email sending fails, the ticket action is still completed
        and persistent (not rolled back).
        """
        mock_send_mail.side_effect = Exception("SMTP server down")
        
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        client.force_login(init_data['agent_user'])
        comments_count_before = ticket.comentarios.count()
        
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(reverse('agregar_comentario', args=[ticket.id]), {'texto': "Comentario seguro"})
            
        # Check action succeeded and comment was saved
        assert response.status_code in [200, 204]
        assert ticket.comentarios.count() == comments_count_before + 1


from tickets.models import PrioridadSLA
from django.utils import timezone
from datetime import timedelta

@pytest.mark.django_db
class TestSLAPriority:
    def test_sla_deadline_calculation(self, init_data):
        """
        Verify that deadline is calculated correctly based on PrioridadSLA.
        """
        # Ensure priority SLA table has default values
        PrioridadSLA.objects.update_or_create(prioridad='urgente', defaults={'horas_objetivo': 4})
        
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], prioridad='urgente', titulo="Ticket Urgente"
        )
        
        expected_deadline = ticket.creado_en + timedelta(hours=4)
        assert ticket.deadline == expected_deadline

    def test_sla_vencido_recent_and_past(self, init_data):
        """
        Verify recent ticket is 'en_plazo' and past ticket is 'vencido'.
        """
        PrioridadSLA.objects.update_or_create(prioridad='urgente', defaults={'horas_objetivo': 4})
        
        # Recent ticket
        ticket_recent = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], prioridad='urgente', titulo="Ticket Reciente"
        )
        assert ticket_recent.estado_sla == 'en_plazo'
        assert "vence en" in ticket_recent.sla_texto
        
        # Past ticket
        ticket_past = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], prioridad='urgente', titulo="Ticket Viejo"
        )
        # Backdate it using update() as cread_en is auto_now_add
        past_time = timezone.now() - timedelta(hours=5)
        Ticket.objects.filter(id=ticket_past.id).update(creado_en=past_time)
        ticket_past.refresh_from_db()
        
        assert ticket_past.estado_sla == 'vencido'
        assert "vencido hace" in ticket_past.sla_texto

    def test_sla_list_filter_by_scope(self, init_data, client):
        """
        Verify list filter 'vencidos=true' only returns active vencidos within user's scope.
        """
        PrioridadSLA.objects.update_or_create(prioridad='urgente', defaults={'horas_objetivo': 4})
        
        # Create ticket for solic1 (vencido)
        t_solic1_vencido = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], prioridad='urgente', titulo="Solic1 Vencido"
        )
        Ticket.objects.filter(id=t_solic1_vencido.id).update(creado_en=timezone.now() - timedelta(hours=5))
        
        # Create ticket for solic2 (vencido)
        t_solic2_vencido = Ticket.objects.create(
            autor=init_data['solic2'], sector=init_data['sec_ti'], prioridad='urgente', titulo="Solic2 Vencido"
        )
        Ticket.objects.filter(id=t_solic2_vencido.id).update(creado_en=timezone.now() - timedelta(hours=5))
        
        # Create ticket for solic1 (not vencido / en_plazo)
        t_solic1_recent = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], prioridad='urgente', titulo="Solic1 Reciente"
        )
        
        # Login as solic1
        client.force_login(init_data['solic1'])
        
        # Fetch list without filter
        response = client.get(reverse('tickets_list'))
        assert response.status_code == 200
        # solic1 can see their own tickets
        tickets_list = response.context['tickets']
        assert t_solic1_vencido in tickets_list
        assert t_solic1_recent in tickets_list
        assert t_solic2_vencido not in tickets_list # Not their scope
        
        # Fetch list with filter
        response_filtered = client.get(reverse('tickets_list') + '?vencidos=true')
        assert response_filtered.status_code == 200
        tickets_filtered = response_filtered.context['tickets']
        assert t_solic1_vencido in tickets_filtered
        assert t_solic1_recent not in tickets_filtered
        assert t_solic2_vencido not in tickets_filtered

    def test_sla_dashboard_counter_by_scope(self, init_data, client):
        """
        Verify dashboard counter respects user scope.
        """
        PrioridadSLA.objects.update_or_create(prioridad='urgente', defaults={'horas_objetivo': 4})
        
        # Create solic1 vencido
        t_solic1 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], prioridad='urgente', titulo="Solic1 Vencido"
        )
        Ticket.objects.filter(id=t_solic1.id).update(creado_en=timezone.now() - timedelta(hours=5))
        
        # Create solic2 vencido
        t_solic2 = Ticket.objects.create(
            autor=init_data['solic2'], sector=init_data['sec_ti'], prioridad='urgente', titulo="Solic2 Vencido"
        )
        Ticket.objects.filter(id=t_solic2.id).update(creado_en=timezone.now() - timedelta(hours=5))
        
        # Login as solic1
        client.force_login(init_data['solic1'])
        response = client.get(reverse('dashboard'))
        assert response.status_code == 200
        # solic1 should only count their own vencido ticket
        assert response.context['indicadores']['vencidos'] == 1
        
        # Login as agent_user (who has access to sec_ti where both solicitations are located)
        client.force_login(init_data['agent_user'])
        response_agent = client.get(reverse('dashboard'))
        assert response_agent.status_code == 200
        # Agent sees both vencidos
        assert response_agent.context['indicadores']['vencidos'] == 2
from django.core import mail
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from tickets.services import asignar_agente, derivar_ticket, reasignar_sector
from tickets.models import HistorialTicket, Notificacion

@pytest.mark.django_db
class TestAgenteAsignacion:
    def test_asignar_agente_exitoso(self, init_data, django_capture_on_commit_callbacks):
        """
        Verify successful assignment, audit log, and in-app + email notification.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        # Clear outbox
        mail.outbox.clear()
        
        with django_capture_on_commit_callbacks(execute=True):
            asignar_agente(ticket, init_data['agent_user'], init_data['dir_user'])
            
        ticket.refresh_from_db()
        assert ticket.agente_asignado == init_data['agent_user']
        
        # Audit log verification
        audit = HistorialTicket.objects.filter(ticket=ticket, tipo='asignacion').first()
        assert audit is not None
        assert audit.valor_anterior == '—'
        assert audit.valor_nuevo == init_data['agent_user'].email
        
        # Notification verification (in-app)
        notif = Notificacion.objects.filter(destinatario=init_data['agent_user'], tipo='asignacion').first()
        assert notif is not None
        assert f"ticket #{ticket.id}" in notif.mensaje
        
        # Email notification verification
        assert len(mail.outbox) == 1
        assert init_data['agent_user'].email in mail.outbox[0].to

    def test_asignar_agente_no_auto_notificar_self(self, init_data, django_capture_on_commit_callbacks):
        """
        If the agent assigns themselves, no notification is sent.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        mail.outbox.clear()
        Notificacion.objects.all().delete()
        
        with django_capture_on_commit_callbacks(execute=True):
            # agent_user assigns themselves (they are allowed because they belong to sec_ti)
            asignar_agente(ticket, init_data['agent_user'], init_data['agent_user'])
            
        ticket.refresh_from_db()
        assert ticket.agente_asignado == init_data['agent_user']
        
        # No notifications
        assert Notificacion.objects.filter(destinatario=init_data['agent_user'], tipo='asignacion').count() == 0
        assert len(mail.outbox) == 0

    def test_asignar_agente_rechazo_sector_ajeno(self, init_data):
        """
        Reject assignment if the agent does not belong to the ticket's sector.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        # Dynamically create maint_agent belonging to Mantenimiento sector
        maint_agent = get_user_model().objects.create(
            username="maint_agent@13dejulio.edu.ar",
            email="maint_agent@13dejulio.edu.ar",
            rol="agente"
        )
        maint_agent.sectores.add(init_data['sec_maint'])
        
        with pytest.raises(ValidationError) as excinfo:
            asignar_agente(ticket, maint_agent, init_data['dir_user'])
        assert "El agente no pertenece al sector del ticket" in str(excinfo.value)

    def test_asignar_agente_rechazo_actor_permisos(self, init_data):
        """
        Verify that unauthorized actors (solicitante, agent of another sector) cannot assign.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        
        # Dynamically create maint_agent belonging to Mantenimiento sector
        maint_agent = get_user_model().objects.create(
            username="maint_agent@13dejulio.edu.ar",
            email="maint_agent@13dejulio.edu.ar",
            rol="agente"
        )
        maint_agent.sectores.add(init_data['sec_maint'])
        
        # Solicitante tries to assign
        with pytest.raises(ValidationError) as excinfo:
            asignar_agente(ticket, init_data['agent_user'], init_data['solic1'])
        assert "No tienes permisos" in str(excinfo.value)
        
        # Agent of other sector tries to assign
        with pytest.raises(ValidationError) as excinfo:
            asignar_agente(ticket, init_data['agent_user'], maint_agent)
        assert "No tienes permisos" in str(excinfo.value)

    def test_auto_clear_on_derivation_and_reasignment(self, init_data):
        """
        Deriving or reassigning a ticket to another sector must clear the assigned agent to None
        and audit this auto-clear in HistorialTicket.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        asignar_agente(ticket, init_data['agent_user'], init_data['dir_user'])
        assert ticket.agente_asignado == init_data['agent_user']
        
        # Derivar to maintenance sector
        derivar_ticket(ticket, init_data['sec_maint'], init_data['dir_user'])
        ticket.refresh_from_db()
        assert ticket.agente_asignado is None
        
        # Check auto-clear audit log (ordered by -creado_en desc, so the latest is first)
        audit = HistorialTicket.objects.filter(ticket=ticket, tipo='asignacion').first()
        assert audit is not None
        assert audit.valor_anterior == init_data['agent_user'].email
        assert audit.valor_nuevo == '—'

    def test_desasignar(self, init_data, django_capture_on_commit_callbacks):
        """
        Deassigning (agente=None) clears the field, audits the change, and does NOT notify.
        """
        ticket = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI"
        )
        asignar_agente(ticket, init_data['agent_user'], init_data['dir_user'])
        
        mail.outbox.clear()
        Notificacion.objects.all().delete()
        
        with django_capture_on_commit_callbacks(execute=True):
            asignar_agente(ticket, None, init_data['dir_user'])
            
        ticket.refresh_from_db()
        assert ticket.agente_asignado is None
        
        # Audit log exists (latest is first)
        audit = HistorialTicket.objects.filter(ticket=ticket, tipo='asignacion').first()
        assert audit.valor_anterior == init_data['agent_user'].email
        assert audit.valor_nuevo == '—'
        
        # NO notifications sent
        assert Notificacion.objects.filter(tipo='asignacion').count() == 0
        assert len(mail.outbox) == 0

    def test_filtro_asignados_a_mi(self, init_data, client):
        """
        Verify the list filter 'asignados_a_mi=true' respects scopes and returns correct records.
        """
        # Ticket 1: TI, assigned to agent_user
        t1 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI 1"
        )
        asignar_agente(t1, init_data['agent_user'], init_data['dir_user'])
        
        # Ticket 2: TI, not assigned
        t2 = Ticket.objects.create(
            autor=init_data['solic1'], sector=init_data['sec_ti'], titulo="Ticket TI 2"
        )
        
        # Login as agent_user
        client.force_login(init_data['agent_user'])
        
        # Without filter: sees both
        response = client.get(reverse('tickets_list'))
        assert response.status_code == 200
        tickets = response.context['tickets']
        assert t1 in tickets
        assert t2 in tickets
        
        # With filter: sees only assigned to themselves
        response_filtered = client.get(reverse('tickets_list') + '?asignados_a_mi=true')
        assert response_filtered.status_code == 200
        tickets_filtered = response_filtered.context['tickets']
        assert t1 in tickets_filtered
        assert t2 not in tickets_filtered


@pytest.mark.django_db
class TestUserApprovalGate:

    @pytest.fixture
    def setup_data(self):
        # Create a directivo (already approved)
        directivo = Usuario.objects.create(
            username='dir@13dejulio.edu.ar',
            email='dir@13dejulio.edu.ar',
            google_sub='sub-dir',
            rol='directivo',
            estado_aprobacion='aprobado',
            is_active=True
        )
        # Create a solicitante (already approved)
        approved_solic = Usuario.objects.create(
            username='sol_app@13dejulio.edu.ar',
            email='sol_app@13dejulio.edu.ar',
            google_sub='sub-sol-app',
            rol='solicitante',
            estado_aprobacion='aprobado',
            is_active=True
        )
        return {
            'directivo': directivo,
            'approved_solic': approved_solic,
        }

    def test_new_user_login_gets_created_as_pendiente(self):
        from usuarios.auth_backend import GoogleOAuthBackend
        backend = GoogleOAuthBackend()
        
        user = backend._get_or_create_user(
            sub='sub-new-user',
            email='new_user@13dejulio.edu.ar',
            name='New User'
        )
        assert user.estado_aprobacion == 'pendiente'
        assert user.rol == 'solicitante'

    def test_superadmin_bootstrap_gets_approved_immediately(self, settings):
        from usuarios.auth_backend import GoogleOAuthBackend
        settings.SUPERADMIN_EMAILS = ['superadmin@13dejulio.edu.ar']
        backend = GoogleOAuthBackend()
        
        user = backend._get_or_create_user(
            sub='sub-superadmin',
            email='superadmin@13dejulio.edu.ar',
            name='Super Admin'
        )
        assert user.estado_aprobacion == 'aprobado'
        assert user.rol == 'directivo'

    def test_middleware_redirects_unapproved_users(self, client, setup_data):
        pending_user = Usuario.objects.create(
            username='pending@13dejulio.edu.ar',
            email='pending@13dejulio.edu.ar',
            google_sub='sub-pending',
            rol='solicitante',
            estado_aprobacion='pendiente',
            is_active=True,
            _keep_pending_in_tests=True
        )
        
        client.force_login(pending_user)
        
        # Attempt to access dashboard -> Redirect to cuenta_pendiente
        response = client.get(reverse('dashboard'))
        assert response.status_code == 302
        assert response.url == reverse('cuenta_pendiente')
        
        # Attempt to access tickets list -> Redirect
        response2 = client.get(reverse('tickets_list'))
        assert response2.status_code == 302
        
        # Accessing cuenta_pendiente -> OK
        response_ok = client.get(reverse('cuenta_pendiente'))
        assert response_ok.status_code == 200
        
        # Accessing logout -> OK
        response_logout = client.get(reverse('logout'))
        assert response_logout.status_code == 302
        
    def test_directivo_can_approve_pending_user(self, setup_data):
        from usuarios.services import aprobar_usuario
        from usuarios.models import HistorialRol
        
        pending_user = Usuario.objects.create(
            username='pending2@13dejulio.edu.ar',
            email='pending2@13dejulio.edu.ar',
            google_sub='sub-pending2',
            rol='solicitante',
            estado_aprobacion='pendiente',
            is_active=True,
            _keep_pending_in_tests=True
        )
        
        aprobar_usuario(pending_user, 'agente', setup_data['directivo'])
        
        pending_user.refresh_from_db()
        assert pending_user.estado_aprobacion == 'aprobado'
        assert pending_user.rol == 'agente'
        
        log = HistorialRol.objects.filter(usuario=pending_user).first()
        assert log is not None
        assert log.actor == setup_data['directivo']
        assert log.rol_anterior == 'solicitante'
        assert log.rol_nuevo == 'agente'

    def test_directivo_can_reject_pending_user(self, setup_data):
        from usuarios.services import rechazar_usuario
        from usuarios.models import HistorialRol
        
        pending_user = Usuario.objects.create(
            username='pending3@13dejulio.edu.ar',
            email='pending3@13dejulio.edu.ar',
            google_sub='sub-pending3',
            rol='solicitante',
            estado_aprobacion='pendiente',
            is_active=True,
            _keep_pending_in_tests=True
        )
        
        rechazar_usuario(pending_user, setup_data['directivo'])
        
        pending_user.refresh_from_db()
        assert pending_user.estado_aprobacion == 'rechazado'
        assert pending_user.rol == 'solicitante'
        
        log = HistorialRol.objects.filter(usuario=pending_user).first()
        assert log is not None
        assert log.actor == setup_data['directivo']
        assert log.rol_nuevo == 'solicitante'

    def test_actions_restricted_to_unapproved_users(self, setup_data):
        from usuarios.services import aprobar_usuario, rechazar_usuario
        
        # Attempt to reject an already approved directivo -> raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            rechazar_usuario(setup_data['directivo'], actor=setup_data['directivo'])
        assert "ya ha sido aprobado" in str(exc_info.value)
        
        # Attempt to approve an already approved user -> raises ValidationError
        with pytest.raises(ValidationError) as exc_info2:
            aprobar_usuario(setup_data['approved_solic'], 'directivo', actor=setup_data['directivo'])
        assert "ya ha sido aprobado" in str(exc_info2.value)

    def test_unauthorized_user_cannot_approve_or_reject(self, setup_data):
        from usuarios.services import aprobar_usuario, rechazar_usuario
        
        pending_user = Usuario.objects.create(
            username='pending4@13dejulio.edu.ar',
            email='pending4@13dejulio.edu.ar',
            google_sub='sub-pending4',
            rol='solicitante',
            estado_aprobacion='pendiente',
            is_active=True,
            _keep_pending_in_tests=True
        )
        
        # Solicitante tries to approve
        with pytest.raises(ValidationError) as exc_info:
            aprobar_usuario(pending_user, 'agente', actor=setup_data['approved_solic'])
        assert "Solo los directivos" in str(exc_info.value)
        
        # Solicitante tries to reject
        with pytest.raises(ValidationError) as exc_info2:
            rechazar_usuario(pending_user, actor=setup_data['approved_solic'])
        assert "Solo los directivos" in str(exc_info2.value)

