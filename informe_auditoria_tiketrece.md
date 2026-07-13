# Informe de auditoría — Sistema de Tickets de Servicios (Tiketrece)

- **Proyecto:** Tiketrece — Sistema de Tickets de Servicios (Escuela 13 de Julio)
- **Stack:** Django 5.2 · PostgreSQL 16 · HTMX · `google-auth` (OAuth 2.0 / OIDC)
- **Commits auditados:** `7d2ecef` (MVP + seguridad) · `b081bb9` (Etapa 9 P1) · `745492e`+`f381a6a`+`461a565` (Etapa 9 P2) · `61287c9` (adjuntos al crear) · `1513112` (hardening prod) · base `4e7c38c`
- **Fecha:** 2026-07-13
- **Auditor:** Claude (control independiente; no participó del desarrollo)
- **Documentos de referencia:** `spec_sistema_tickets_v2.md`, acta de aprobación Etapa 1

## Método

1. Revisión estática del código de los módulos críticos (auth, servicios, permisos,
   modelos, settings, migraciones).
2. Ejecución de la suite `pytest` en entorno controlado con **PostgreSQL 16 real**
   (para ejercitar la migración de triggers append-only, que es plpgsql).
3. Verificación de que no haya secretos versionados.

## Veredicto: ✅ APROBADO — sin observaciones abiertas

Las 7 condiciones de aprobación se cumplen en la implementación; el hallazgo de
seguridad detectado en la primera pasada fue corregido y verificado; la suite
completa pasa.

---

## 1. Condiciones de aprobación (Etapa 1) — verificación

| # | Condición | Estado | Evidencia |
|---|-----------|:------:|-----------|
| 1 | Mock de OAuth gateado por `ENABLE_MOCK_AUTH` (default False) + `raise` si mock con `DEBUG=False` | ✅ | `config/settings.py:46-47` y `apps/usuarios/auth_backend.py:16-17` (doble chequeo) |
| 2 | El mock solo emite identidades `@13dejulio.edu.ar` | ✅ | `apps/usuarios/auth_backend.py:20-23` |
| 3 | Verificación real del ID token: firma/`aud`/`iss`/`exp` + `email_verified` + `hd` | ✅ | `apps/usuarios/auth_backend.py:33-59` |
| 4 | RF-16 (baja de sector con tickets abiertos) en capa de servicios, no solo `clean()` | ✅ | `apps/sectores/services.py:11-16` + `models.py:24-26` (`full_clean` en `save`) |
| 5 | RF-17 (nunca sin directivos; superadmin no degradable) + auditoría en `HistorialRol` | ✅ | `apps/usuarios/services.py:15-35` |
| 6 | Reasignación directiva (RF-08) y prioridad global (RF-09) con alcance global | ✅ | `apps/tickets/services.py:149-177` (`reasignar_sector`), `:98` |
| 7 | Auditoría append-only en `transaction.atomic` con actor | ✅ | todos los servicios escriben `HistorialTicket`/`HistorialRol`; **además** triggers DB (ver §3) |

## 2. Hallazgo de seguridad (detectado y corregido)

**`state` de OAuth constante (CSRF).** En la primera versión, `google_login_redirect`
generaba el `state` a partir de `hash(SECRET_KEY)` — el mismo valor para todas las
sesiones, lo que anula la protección CSRF del login.

- **Severidad:** media.
- **Corrección (commit `7d2ecef`):** `apps/usuarios/views.py:52` → `secrets.token_urlsafe(32)`
  (nonce aleatorio por request; el callback ya validaba y consumía el `state`).
- **Tests que lo cubren:** `test_oauth_state_is_unique`, `test_oauth_callback_rejects_mismatched_state`.

## 3. Observaciones menores (todas resueltas)

| Obs. | Descripción | Resolución (commit `7d2ecef`) |
|------|-------------|-------------------------------|
| M-1 | `is_staff` auto-asignado a directivos abría `/admin/` sin necesidad | Removido de `apps/usuarios/models.py` (`save` deja `is_staff` en default) |
| M-2 | Comparación de dominio sensible a mayúsculas | `.lower()` en mock y verificación real (`auth_backend.py:22,54,58`) |
| M-3 | Append-only solo a nivel aplicación (era opcional) | Migración `apps/tickets/migrations/0003_...`: triggers plpgsql que bloquean `UPDATE`/`DELETE` en `historial_ticket` e `historial_rol` |
| M-4 | Lógica de alcance duplicada | `es_gestor_o_autor` centralizado en `apps/tickets/permissions.py`; `services.py` lo importa |

## 4. Resultado de la suite de tests

Ejecutada por el auditor contra PostgreSQL 16 real:

```
28 passed in 1.29s
```

Cobertura por archivo (6 archivos, 28 tests):

| Archivo | Cubre |
|---------|-------|
| `test_auth.py` (8) | mock inerte en prod, rechazo de dominio en mock, verificación real (dominio + `email_verified`), unicidad del `state`, rechazo de `state` no coincidente, append-only a nivel DB (update/delete) |
| `test_governance.py` (5) | superadmin no degradable por no-superadmin, degradable por otro superadmin, no quedar sin directivos (rol y desactivación), auditoría de rol |
| `test_permissions.py` (4) | visibilidad por alcance, agente no modifica tickets ajenos, acciones globales del directivo (RF-08/09), regla "relacionado" de comentarios (RF-10) |
| `test_sectors.py` (3) | RF-16 por servicio y por `save()`, baja exitosa con solo cerrados |
| `test_ticket_flow.py` (4) | transiciones válidas, inválidas rechazadas, cierre solo desde `resuelto`, cierre/reapertura por actor autorizado |
| `test_audit.py` (4) | registro de auditoría en estado/prioridad/derivación/reasignación con actor y valores |

## 5. Higiene del repositorio

- **Sin secretos versionados:** `.env` excluido por `.gitignore`; no hay archivos con
  credenciales en el árbol (verificado).
- **CI:** GitHub Actions levanta PostgreSQL y corre la suite en cada push
  (`.github/workflows/ci.yml`).

## 6. Etapa 9 — Parte 1 (búsqueda de texto + export CSV) · commit `b081bb9`

Feature post-MVP auditada por separado. **Estado: ✅ APROBADA, sin observaciones abiertas.**

**Alcance de la entrega:** búsqueda de texto en el listado (título + descripción),
exportación del listado a CSV respetando alcance y filtros, alineación del permiso
`puede_cambiar_estado` con el servicio, y test de humo de UI.

**Hallazgo de seguridad (planteado en la revisión del plan y ya resuelto):**
*CSV formula injection.* El `titulo` es texto libre del usuario; una celda que empiece
con `= + - @` (o tab/CR) puede ejecutarse como fórmula al abrir el CSV en Excel. Se
incorporó `sanitize_csv_cell` que neutraliza esas celdas con un apóstrofo. Verificado
por test (`=1+1` → `'=1+1`).

**Verificación por condición:**

| Ítem | Estado | Evidencia |
|------|:------:|-----------|
| Alcance antes de filtros (búsqueda) | ✅ | `apps/tickets/views.py` — `q` sobre `obtener_tickets_visibles(user)` |
| Export: alcance antes de filtros | ✅ | `export_tickets_csv_view`; test de bypass por `?autor=` da 0 filas |
| CSV formula injection | ✅ | `sanitize_csv_cell` (`= + - @ \t \r` → `'`); test dedicado |
| BOM UTF-8 + streaming | ✅ | `﻿` una vez + `StreamingHttpResponse` + `select_related` |
| `puede_cambiar_estado` alineado al servicio | ✅ | solicitante-autor solo con estado `resuelto`/`cerrado` |
| Test de humo de UI | ✅ | detalle como directivo muestra controles de prioridad/reasignar; listado muestra búsqueda + export |

**Suite de tests:** **36/36 en verde** (28 del MVP + 8 de Etapa 9), corrida por el
auditor contra PostgreSQL 16 real.

## 7. Etapa 9 — Parte 2 (notificaciones + adjuntos) · commits `745492e`, `f381a6a`, `461a565`, `61287c9`

**Estado: ✅ APROBADA, sin observaciones abiertas.**

**Notificaciones in-app (`745492e`):** generación en la capa de servicios dentro del
`transaction.atomic`, dirigida a autor + agentes del sector (origen y destino en
derivación/reasignación), excluyendo al actor y filtrando por `is_active`. Lista,
contador y "marcar" filtrados por `request.user`, con guard **IDOR**
(`get(pk, destinatario=request.user)` → `Http404`).

**Adjuntos (`f381a6a` + fix `461a565`):** validación por **magic bytes** en servidor
(SVG/exe/html rechazados), `seek(0)` antes de guardar, almacenamiento con **UUID**
(sin path traversal), **descarga por vista autenticada** con `puede_ver_ticket`
(`/media/` NO público), `Content-Disposition: attachment` + `nosniff`. Hallazgo del
auditor resuelto: `MEDIA_ROOT`/`MEDIA_URL` no estaban definidos (riesgo de que
adjuntos con datos personales cayeran fuera de `media/` y se commitearan) →
configurados y verificados por test.

**Adjuntos al crear ticket (`61287c9`):** subida opcional (hasta 5) en la creación,
con **pre-validación de todos los archivos antes** del `transaction.atomic` (sin
tickets a medias ni huérfanos) y helper `guardar_adjunto` reutilizado en creación y
detalle (DRY). Input con `accept` + `capture` para cámara en móvil.

## 8. Hardening de producción · commit `1513112`

**Estado: ✅ APROBADO.**

`config/settings.py` incorpora, **gateado a `DEBUG=False`** (no afecta dev ni tests):
`SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, cookies `Secure` (sesión y CSRF),
HSTS (1 año + subdominios + preload), `SECURE_CONTENT_TYPE_NOSNIFF`,
`X_FRAME_OPTIONS='DENY'` y `CSRF_TRUSTED_ORIGINS`. `ALLOWED_HOSTS` se lee de entorno
con default **fail-closed** (`[]`) en producción.

Verificación del auditor:
- Suite con `DEBUG=True`: **51/51 en verde** (el gating no afecta dev/tests).
- `manage.py check --deploy --fail-level WARNING` con `DEBUG=False` + clave fuerte:
  **"System check identified no issues"** — deploy checks 100% limpios.

## 9. Conclusión

El MVP (Etapa 8), la **Etapa 9 completa** (búsqueda + export CSV, notificaciones,
adjuntos y adjuntos al crear) y el **hardening de producción** fueron auditados y
aprobados. Todos los hallazgos de seguridad detectados por el auditor —state CSRF
constante, CSV formula injection, `MEDIA_ROOT` sin configurar— fueron corregidos y
verificados. La base es sólida, auditable y con cobertura de tests de los flujos
críticos (**51/51 en verde** contra PostgreSQL real) y los deploy checks de Django
limpios. **Apto para uso interno** una vez configurada la OAuth App de producción y
realizado el despliegue.

### Pendientes que dependen del usuario (no bloquean la aprobación técnica)

1. Crear la OAuth App en Google Cloud Console y cargar `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET` + redirect URI de producción (https).
2. Definir dominio/URL de despliegue y cargar `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`.
3. Desplegar según la receta (Proxmox + Nginx/TLS, o VPN/Cloudflare Access); en prod
   `DEBUG=False`, `ENABLE_MOCK_AUTH=False`, `SECRET_KEY` fuerte.
