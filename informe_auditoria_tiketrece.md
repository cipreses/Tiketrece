# Informe de auditoría — Sistema de Tickets de Servicios (Tiketrece)

- **Proyecto:** Tiketrece — Sistema de Tickets de Servicios (Escuela 13 de Julio)
- **Stack:** Django 5.2 · PostgreSQL 16 · HTMX · `google-auth` (OAuth 2.0 / OIDC)
- **Commit auditado:** `7d2ecef` (posterior a las correcciones) · base previa `4e7c38c`
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

## 6. Conclusión

El MVP (Etapa 8) cumple la especificación v2 y las condiciones de aprobación de la
Etapa 1, con la única falla de seguridad detectada ya corregida y verificada. La base
es sólida, auditable y con cobertura de tests de los flujos críticos. **Apto para
continuar** con las siguientes etapas (integración de credenciales reales de Google,
despliegue) y para uso interno una vez configurada la OAuth App de producción.

### Pendientes que dependen del usuario (no bloquean la aprobación técnica)

1. Crear la OAuth App en Google Cloud Console y cargar `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET` + redirect URI de producción.
2. Definir dominio/URL de despliegue.
3. En producción: `DEBUG=False`, `ENABLE_MOCK_AUTH=False`, `SECRET_KEY` fuerte,
   `ALLOWED_HOSTS` acotado (hoy `['*']`).
