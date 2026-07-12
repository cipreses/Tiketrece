# Spec técnico v2: Sistema de Tickets de Servicios (gestión por sectores)

> Documento de requerimientos para que una IA lo implemente. Dividido en
> **etapas incrementales**. El MVP (Etapas 2–9) es obligatorio; las Etapas 10–11
> son mejoras posteriores. El stack es **agnóstico** salvo las restricciones de
> las Etapas 0 y 0.5 y el **GATE de aprobación** (Etapa 1).
>
> **Esta es la v2.** Reescribe la v1 para cerrar ambigüedades de autorización,
> corregir el modelo de datos y endurecer la autenticación. Los cambios respecto
> de la v1 están resumidos abajo (§ Registro de cambios v2) y marcados en el
> cuerpo con la etiqueta **[v2]**. Las decisiones tomadas por el usuario se
> marcan **[Decisión v2]**; las que la IA asumió con un default razonable y el
> usuario aún puede revertir, **[Asumido v2]**.

---

## Registro de cambios v2

| # | Tema | Qué cambió respecto de la v1 | Origen |
|---|------|------------------------------|--------|
| C-01 | **Comentarios** | Se define "relacionado": el solicitante comenta en *sus* tickets; agentes/directivos, en tickets de su(s) sector(es); el directivo, en cualquiera. | Decisión 1A |
| C-02 | **Cierre / reapertura** | Cierra el **autor o un gestor** (agente del sector / directivo) **solo desde `resuelto`**. Reabre el autor o un gestor (`cerrado → en_progreso`). | Decisión 2A |
| C-03 | **Baja de sector** | No se puede desactivar un sector con tickets **abiertos**: primero hay que cerrarlos o reasignarlos. | Decisión 3A |
| C-04 | **Agente ↔ sector** | Relación **N–N** vía tabla puente `usuario_sector` (un agente puede cubrir varios sectores). Se elimina el `sector_id` único del `Usuario`. | Decisión 4A |
| C-05 | **Autenticación** | Validación endurecida: firma del ID token + `aud` = `client_id` + `email_verified == true`, y `hd` preferido sobre el match por dominio del email. | Asumido |
| C-06 | **Auditoría / historial** | Se reemplaza la tabla `Derivacion` por `historial_ticket` unificada, que audita **estado, prioridad y sector** (antes el estado no se auditaba). | Asumido |
| C-07 | **Gobernanza de roles** | Los cambios de rol se auditan; el sistema **nunca queda sin directivos**; el **superadmin no puede ser degradado** por un no-superadmin. | Asumido |
| C-08 | **Matriz de permisos** | Se agrega una matriz explícita actor × acción × **alcance** (sobre qué tickets) para eliminar zonas grises de autorización. | Asumido |

---

## Etapa 0 — Contexto y objetivo

Sistema para registrar y gestionar **solicitudes de servicio** de distintos
tipos dirigidas a distintos **sectores** de una **organización educativa**.

- El **solicitante** abre un ticket y elige el **sector** y la **prioridad**.
- El **sector** asignado gestiona el ticket, puede **cambiar la prioridad** y
  **derivarlo** a otro sector si corresponde.
- El **Equipo Directivo** puede **reasignar** tickets a cualquier sector y
  **cambiar la prioridad** de cualquier ticket de la organización.
- Cada ticket tiene historial de comentarios, una **máquina de estados** que
  avanza hasta su cierre, y un **historial de auditoría** de todos sus cambios
  de estado, prioridad y sector.

### Autenticación (RESTRICCIÓN OBLIGATORIA)
- El acceso al sistema se valida **exclusivamente a través de una cuenta de
  Google**, y **solo se aceptan usuarios cuyo email pertenezca al dominio
  `13dejulio.edu.ar`**.
- No se implementa registro ni login con usuario/contraseña locales.
- El flujo es **Google OAuth 2.0** (OpenID Connect). En el callback se valida el
  ID token y la pertenencia al dominio (detalle endurecido en la Etapa 7).
- El primer inicio de sesión de un email válido crea el registro de usuario
  (rol por defecto `solicitante`); un `directivo` lo promueve a `agente`/`directivo`.

**Fuera de alcance (v1):** notificaciones automáticas, SLA por prioridad,
pagos, integraciones externas. (Ver Etapas 10–11.)

---

## Etapa 0.5 — Decisiones ya CERRADAS (la IA NO debe re-proponerlas)

> Decisiones tomadas por el usuario (Julio), **definitivas**. La IA las respeta
> tal cual; no las debate ni las ofrece como opciones en la Etapa 1. Solo se
> reabren si el usuario lo pide explícitamente.

| # | Decisión cerrada | Detalle obligatorio |
|---|------------------|---------------------|
| D-01 | **Proveedor de identidad** | Google (OAuth 2.0 / OpenID Connect). Sin login por usuario/contraseña. |
| D-02 | **Dominio permitido** | Únicamente `@13dejulio.edu.ar`. Rechazo explícito de cualquier otro dominio. |
| D-03 | **Gestión de la OAuth App** | El usuario la crea y administra en **Google Cloud Console**. La IA **solo consume** credenciales por variables de entorno. |
| D-04 | **Superadmin de setup** | `ti@13dejulio.edu.ar`, reconocido vía `SUPERADMIN_EMAILS` (config/env). Es un `directivo` con permisos totales de setup. |
| D-05 | **Sectores iniciales** | Secretaría, TI, Mantenimiento, Talleres, Laboratorio, Equipo Directivo, Preceptorías, Regencia. Configurables (no hardcodeados). |
| D-06 | **Roles del sistema** | `solicitante`, `agente` (de sector), `directivo`. Superadmin = directivo con flag de setup. |
| D-07 | **Campos del ticket** | sector, prioridad (baja/media/alta/urgente), título, descripción, estado, comentarios, derivación. |
| D-08 | **Máquina de estados** | abierto → en_progreso / en_espera → resuelto → cerrado, con reapertura. (Ver Etapa 6.) |
| D-09 | **GATE de aprobación** | Arquitectura, entorno, lenguajes y tecnologías deben ser **propuestos y aprobados por el usuario antes de programar**. |
| D-10 | **Sectores configurables** | La lista de sectores se edita por backend o archivo de configuración; nunca como constante en el código. |

---

## Etapa 1 — Aprobación de arquitectura, entorno y tecnologías (GATE OBLIGATORIO)

> **La IA implementadora NO debe comenzar a programar hasta cumplir esta etapa.**

Las decisiones de la **Etapa 0.5 están cerradas** y no forman parte de esta
propuesta. La IA solo propone y debate lo **abierto**:

1. **Arquitectura:** tipo (monolito web, cliente/servidor separados, serverless…),
   capas (datos / lógica / vista) y cómo se comunican.
2. **Entorno de desarrollo:** sistema operativo objetivo, runtime, gestor de
   paquetes, herramientas recomendadas.
3. **Lenguajes** de backend y frontend.
4. **Frameworks y librerías clave**, justificando cada elección.
5. **Base de datos** (motor, esquema inicial, migraciones). **[v2]** Se
   recomienda **el mismo motor en dev y en prod** (evitar SQLite-en-dev /
   Postgres-en-prod) para no arrastrar diferencias de comportamiento.
6. **Autenticación (detalle de implementación):** cómo se integra Google
   OAuth 2.0 y la restricción de dominio dentro del stack elegido (librería
   cliente, verificación del ID token, manejo de tokens/sesiones, dónde se
   guarda la identidad, y **qué variables de entorno** espera la app:
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, redirect URI, `SUPERADMIN_EMAILS`).
7. **Estrategia de pruebas y CI. [v2]** Qué framework de tests se usa y qué
   flujos críticos se cubren (ver Etapa 10). Un CI mínimo que corra los tests.
8. **Despliegue objetivo** (local, servidor, nube) y requisitos para levantarlo.
9. **Estructura del repositorio** y convenciones.

**Regla de oro:** cualquier cambio significativo de stack, lenguaje o
arquitectura durante el desarrollo debe ser **re-propuesto y re-aprobado**
por el usuario antes de aplicarse.

---

## Etapa 2 — Requisitos funcionales

| ID | Requisito | Prioridad |
|----|-----------|-----------|
| RF-01 | Iniciar sesión únicamente con Google, dominio `13dejulio.edu.ar` | Obligatorio |
| RF-02 | Existen roles: `solicitante`, `agente` (de sector) y `directivo` | Obligatorio |
| RF-03 | Un solicitante crea un ticket eligiendo sector, prioridad, título y descripción | Obligatorio |
| RF-04 | Un ticket pertenece a un único sector a la vez | Obligatorio |
| RF-05 | Un agente puede cambiar el estado de un ticket **solo si el ticket pertenece a uno de sus sectores** (el directivo, en cualquiera) **[v2]** | Obligatorio |
| RF-06 | Un agente puede derivar a otro sector un ticket **de uno de sus sectores** **[v2]** | Obligatorio |
| RF-07 | Un agente puede cambiar la prioridad de un ticket **de uno de sus sectores** (el directivo, en cualquiera) **[v2]** | Obligatorio |
| RF-08 | El Equipo Directivo puede reasignar cualquier ticket a otro sector | Obligatorio |
| RF-09 | El Equipo Directivo puede cambiar la prioridad de cualquier ticket | Obligatorio |
| RF-10 | Agregar comentarios a un ticket, **según la regla de "relacionado"**: el solicitante en sus propios tickets; un agente/directivo en tickets de su(s) sector(es); el directivo en cualquiera **[v2 · Decisión 1A]** | Obligatorio |
| RF-11 | Listar tickets con filtros (sector, estado, autor, prioridad), ordenados por `actualizado_en` desc | Obligatorio |
| RF-12 | Dashboard con métricas básicas por sector, estado y prioridad | Obligatorio |
| RF-13 | Los sectores son configurables (alta/baja/modificación) vía backend o archivo de configuración | Obligatorio |
| RF-14 | Un `directivo` (incl. superadmin) puede promover/bajar el rol de otros usuarios, **respetando las invariantes de gobernanza** (RF-17) **[v2]** | Obligatorio |
| RF-15 | **[v2]** Cada cambio de **estado, prioridad o sector** de un ticket queda registrado en un **historial de auditoría** (quién, cuándo, valor anterior → nuevo) | Obligatorio |
| RF-16 | **[v2 · Decisión 3A]** No se puede **desactivar un sector** que tenga tickets **abiertos** (no `cerrado`): primero deben cerrarse o reasignarse | Obligatorio |
| RF-17 | **[v2]** Invariantes de gobernanza de roles: (a) el sistema **nunca queda sin al menos un `directivo` activo**; (b) el **superadmin no puede ser degradado** por un no-superadmin; (c) todo cambio de rol se **audita** | Obligatorio |

## Etapa 3 — Requisitos no funcionales

- **RN-01** Persistencia de datos (base de datos relacional o equivalente).
- **RN-02** Autenticación **exclusiva** vía Google OAuth 2.0; no se almacenan
  contraseñas locales.
- **RN-03** Autorización por rol **y por alcance** (sector) en cada
  endpoint/pantalla. Ver la **matriz de permisos** de la Etapa 5. **[v2]**
- **RN-04** Interfaz usable desde navegador (web responsive).
- **RN-05** El código debe ser ejecutable y reproducible (README con pasos).
- **RN-06** La lista de sectores debe ser fuente de datos configurable, no
  constante en el código.
- **RN-07** Restricción estricta de dominio: solo emails `@13dejulio.edu.ar`
  pueden autenticarse; el rechazo debe ser explícito y seguro (Etapa 7).
- **RN-08** Las credenciales de la OAuth App de Google se proveen por variables
  de entorno; el usuario las gestiona en Google Cloud Console.
- **RN-09** **[v2]** El ID token de Google se **verifica criptográficamente**
  (firma, `aud`, `iss`, expiración) antes de confiar en sus claims; se exige
  `email_verified == true`. No se confía en datos del cliente sin verificar.
- **RN-10** **[v2]** Existe un **historial de auditoría** inmutable de los
  cambios sensibles (estado/prioridad/sector de tickets y cambios de rol de
  usuarios): append-only, con actor y timestamp.
- **RN-11** **[v2]** Pruebas automatizadas de los flujos críticos y un CI
  mínimo que las ejecute (ver Etapa 10, criterio 6).

---

## Etapa 4 — Modelo de datos

Entidades sugeridas (la IA puede ajustar nombres, no la semántica):

### Usuario
- `id`, `google_sub` (subject único de Google), `email` (único, dominio
  verificado), `nombre`
- `rol`: `solicitante` | `agente` | `directivo`
- `es_superadmin`: booleano (derivado de `SUPERADMIN_EMAILS`, p. ej. `ti@13dejulio.edu.ar`)
- `activo`: booleano (para baja lógica sin perder trazabilidad)
- **Sin `sector_id`** — la pertenencia a sectores se modela aparte (ver
  `usuario_sector`). **[v2 · Decisión 4A]**
- Sin contraseña: la identidad viene de Google.

### usuario_sector  **[v2 · Decisión 4A]**
Tabla puente **N–N** entre agentes y sectores (un agente puede cubrir varios).
- `usuario_id`, `sector_id`
- PK compuesta (`usuario_id`, `sector_id`).
- Solo aplica a usuarios con rol `agente` (un `directivo` tiene alcance global y
  no necesita filas acá; un `solicitante` no gestiona sectores).

### Sector
- `id`, `nombre`, `descripcion`, `activo` (baja lógica sin borrar)
- Relación: un sector tiene muchos agentes (vía `usuario_sector`) y muchos `Ticket`.
- **Configurable** vía backend o archivo de configuración (RF-13).
- **Invariante [v2 · Decisión 3A]:** no puede pasar a `activo = false` si tiene
  tickets en estado distinto de `cerrado`.

### Ticket
- `id`, `titulo`, `descripcion`
- `sector_id` (sector actual)
- `autor_id` (quien lo creó)
- `prioridad`: `baja` | `media` | `alta` | `urgente` (default `media`)
- `estado`: `abierto` | `en_progreso` | `en_espera` | `resuelto` | `cerrado`
- `creado_en`, `actualizado_en`, `cerrado_en` (nullable)
- `derivado_desde_sector_id` (nullable, conveniencia del último origen; la
  traza completa vive en `historial_ticket`)

### Comentario
- `id`, `ticket_id`, `autor_id`, `texto`, `creado_en`

### historial_ticket  **[v2 · reemplaza a `Derivacion`]**
Auditoría **unificada** de los cambios de un ticket. Un registro por cambio.
- `id`, `ticket_id`, `actor_id`, `creado_en`
- `tipo`: `estado` | `prioridad` | `sector`
- `valor_anterior` (text/nullable), `valor_nuevo` (text)
- Notas:
  - Un cambio de **estado** guarda `tipo='estado'`, `abierto → en_progreso`, etc.
  - Un cambio de **prioridad** guarda `tipo='prioridad'`, `media → alta`, etc.
  - Una **derivación** o **reasignación directiva** guarda `tipo='sector'`,
    con los `id`/nombres de sector origen y destino.
  - Es **append-only** (RN-10): no se edita ni borra.

### historial_rol  **[v2]**
Auditoría de los cambios de rol de usuarios (RF-14/RF-17).
- `id`, `usuario_id` (afectado), `actor_id` (quién lo cambió), `creado_en`
- `rol_anterior`, `rol_nuevo`

> Alternativa de diseño: `historial_rol` puede fusionarse con `historial_ticket`
> en una única tabla `auditoria(entidad, entidad_id, tipo, valor_anterior,
> valor_nuevo, actor_id, creado_en)`. La IA puede elegir, manteniendo la
> semántica append-only y la trazabilidad.

---

## Etapa 5 — Actores, roles y **matriz de permisos** **[v2]**

Roles: `solicitante`, `agente`, `directivo`. El **superadmin** es un `directivo`
señalado en `SUPERADMIN_EMAILS`, con permisos adicionales de **setup**
(gestionar sectores y roles). Toda cuenta válida entra primero como
`solicitante` y es promovida por un `directivo`/superadmin.

**Alcance ("sobre qué tickets"):**
- **propios** = tickets donde el usuario es `autor`.
- **de sector** = tickets cuyo `sector_id` está entre los sectores del agente
  (`usuario_sector`).
- **global** = todos los tickets de la organización.

| Acción | solicitante | agente | directivo |
|--------|-------------|--------|-----------|
| Crear ticket (elige sector y prioridad) | ✅ | ✅ | ✅ |
| Ver ticket | propios | de sector | global |
| Comentar (RF-10) | propios | de sector | global |
| Cambiar **estado** (según máquina de estados) | ❌ | de sector | global |
| Cambiar **prioridad** | ❌ | de sector | global |
| **Derivar** a otro sector | ❌ | de sector | global |
| **Reasignar** sector (override) | ❌ | ❌ | global |
| **Cerrar** ticket (solo desde `resuelto`) | propios | de sector | global |
| **Reabrir** ticket (`cerrado → en_progreso`) | propios | de sector | global |
| Gestionar sectores (CRUD) | ❌ | ❌ | ✅ (setup) |
| Gestionar roles de usuarios (RF-14) | ❌ | ❌ | ✅ (con RF-17) |

**Notas [v2]:**
- **Cierre/Reapertura (Decisión 2A):** los realiza el **autor del ticket** o un
  **gestor** (agente de su sector / directivo). El cierre **solo** es válido
  desde `resuelto`; la reapertura lleva `cerrado → en_progreso`.
- El **directivo** siempre tiene visibilidad y acción **global**.
- El **superadmin** (`ti@13dejulio.edu.ar`, configurable vía `SUPERADMIN_EMAILS`)
  es un `directivo` con permisos de setup; no es un rol aparte.

---

## Etapa 6 — Flujo de un ticket y máquina de estados

1. El solicitante crea el ticket eligiendo **sector**, **prioridad**, **título**
   y **descripción**.
2. El ticket entra en `abierto`, asignado al sector elegido, con esa prioridad.
3. Un agente de ese sector lo toma (`en_progreso`) y trabaja sobre él.
4. Si no corresponde a su sector, lo **deriva** (cambia `sector_id`; queda en
   `historial_ticket` con `tipo='sector'`).
5. El agente puede **subir/bajar la prioridad** (queda en `historial_ticket`).
6. El agente puede pedir info (`en_espera`) o marcarlo `resuelto`.
7. **Cierre [v2 · Decisión 2A]:** desde `resuelto`, el **autor** o un **gestor**
   lo pasa a `cerrado` y se setea `cerrado_en`.
8. **Reapertura [v2 · Decisión 2A]:** desde `cerrado`, el **autor** o un
   **gestor** puede reabrir (`cerrado → en_progreso`).
9. El **Equipo Directivo** puede, en cualquier momento, reasignar el sector o
   sobrescribir la prioridad de cualquier ticket (queda auditado).

**Transiciones válidas (máquina de estados):**
```
abierto      → en_progreso
abierto      → en_espera
en_progreso  → en_espera
en_progreso  → resuelto
en_espera    → en_progreso
resuelto     → cerrado        (cierre: autor o gestor)   [v2]
cerrado      → en_progreso    (reapertura: autor o gestor) [v2]
```
- El backend **debe** rechazar cualquier transición fuera de esta lista.
- La **prioridad** se puede modificar en cualquier estado; toda modificación
  (estado, prioridad o sector) queda registrada en `historial_ticket` (RF-15).

---

## Etapa 7 — Autenticación Google (detalle endurecido) **[v2]**

- Usar **Google OAuth 2.0 / OpenID Connect** (librería cliente oficial o
  estándar del stack elegido). Flujo Authorization Code.
- **Verificar el ID token antes de confiar en sus claims (RN-09):**
  1. **Firma** válida contra las claves públicas de Google.
  2. **`aud`** == tu `GOOGLE_CLIENT_ID`.
  3. **`iss`** ∈ `{accounts.google.com, https://accounts.google.com}`.
  4. **No expirado** (`exp`).
  5. **`email_verified == true`.**
- **Restricción de dominio (RN-07):** aceptar **solo** si
  `hd == "13dejulio.edu.ar"`. Si el proveedor no envía `hd`, exigir que el
  dominio del `email` verificado sea exactamente `13dejulio.edu.ar`. Cualquier
  otro caso → **rechazo explícito** (no crear usuario, no iniciar sesión).
  Se prefiere el claim `hd` por sobre el match textual del email.
- **Mapear** la identidad de Google (`sub` + email + nombre) a un `Usuario`
  local (crear si no existe, con rol `solicitante`; marcar `es_superadmin` si el
  email está en `SUPERADMIN_EMAILS`). La clave estable es `google_sub`, no el
  email (el email podría cambiar).
- Mantener la sesión del lado del servidor (cookie firmada / token de sesión);
  no exponer el token de Google al cliente de forma insegura.
- No almacenar contraseñas bajo ningún concepto.
- Credenciales (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, redirect URI) por
  **variables de entorno**; el usuario las obtiene de su OAuth App en Google
  Cloud Console. La IA no las genera.

---

## Etapa 8 — MVP: funcionalidades a implementar

### 8.1 Login Google + roles (RF-01, RF-02, RN-02/03/07/09, RF-14, RF-17)
- [ ] Flujo "Iniciar sesión con Google".
- [ ] **Verificación del ID token** (firma, `aud`, `iss`, `exp`, `email_verified`). **[v2]**
- [ ] Restricción estricta de dominio `13dejulio.edu.ar` (`hd` preferente; rechazo explícito). **[v2]**
- [ ] Creación automática de `Usuario` en primer login (rol `solicitante`).
- [ ] Reconocer `ti@13dejulio.edu.ar` como superadmin vía `SUPERADMIN_EMAILS`.
- [ ] Gestión de roles por `directivo`/superadmin con invariantes de gobernanza. **[v2]**
- [ ] Auditoría de cambios de rol (`historial_rol`). **[v2]**
- [ ] Middleware/guard que proteja rutas por **rol y alcance** (matriz Etapa 5). **[v2]**

### 8.2 Configuración de sectores (RF-13, RN-06, RF-16)
- [ ] Los sectores se cargan desde backend o archivo de configuración.
- [ ] CRUD básico de sectores (alta/baja/modificación) por directivo/superadmin.
- [ ] **Guarda de baja:** no permitir desactivar un sector con tickets abiertos. **[v2]**
- [ ] El listado de sectores en formularios se obtiene de la fuente configurable.

### 8.3 Creación de ticket (RF-03, RF-04)
- [ ] Formulario: selector de sector, selector de prioridad, título, descripción.
- [ ] Validación: sector existe y está **activo**; título no vacío; prioridad en el enum.
- [ ] Al crear → estado `abierto`, `autor_id` = usuario actual, prioridad elegida.

### 8.4 Gestión por sector, prioridad y derivación (RF-05, RF-06, RF-07, RF-15)
- [ ] Vista de tickets filtrada a **los sectores** del agente. **[v2]**
- [ ] "Cambiar estado" respetando la máquina de estados (Etapa 6) → registra en `historial_ticket`. **[v2]**
- [ ] "Cambiar prioridad" → registra en `historial_ticket`.
- [ ] "Derivar a sector" (actualiza `sector_id`) → registra en `historial_ticket`.
- [ ] Toda acción valida **alcance de sector** antes de ejecutar. **[v2]**

### 8.5 Reasignación y prioridad global (RF-08, RF-09, RF-15)
- [ ] El Equipo Directivo reasigna cualquier ticket a cualquier sector.
- [ ] El Equipo Directivo cambia la prioridad de cualquier ticket.
- [ ] Ambas acciones registradas en `historial_ticket`. **[v2]**

### 8.6 Comentarios (RF-10)
- [ ] Comentar según la regla de "relacionado" (solicitante→propios; agente/directivo→de sector/global). **[v2]**
- [ ] El comentario queda con `autor_id` y `creado_en`.

### 8.7 Listado y filtros (RF-11)
- [ ] Listar tickets con filtros por: sector, estado, autor, prioridad.
- [ ] Orden por `actualizado_en` desc.
- [ ] El listado respeta el **alcance** del usuario (un solicitante solo ve los propios). **[v2]**

### 8.8 Dashboard (RF-12)
- [ ] Conteo de tickets por estado y por sector.
- [ ] Conteo por prioridad.
- [ ] Indicadores: abiertos, en progreso, resueltos, cerrados.
- [ ] (Opcional) Tendencia por fecha de creación.

### 8.9 Cierre y reapertura (RF-15, Decisión 2A) **[v2]**
- [ ] "Cerrar" habilitado **solo desde `resuelto`**, para autor o gestor; setea `cerrado_en`.
- [ ] "Reabrir" (`cerrado → en_progreso`) para autor o gestor.
- [ ] Ambas transiciones registradas en `historial_ticket`.

---

## Etapa 9 — Extras (post-MVP, sugeridos)

- **SLA por prioridad:** tiempos objetivo de resolución según prioridad.
- **Notificaciones:** email o interna al cambiar estado/prioridad/comentar/derivar/reasignar.
- **Adjuntos:** el solicitante puede subir archivos al ticket.
- **Búsqueda de texto:** full-text sobre título/descripción/comentarios.
- **Reportes:** exportar a CSV/PDF por sector, prioridad y rango de fechas.
- **API pública:** endpoints REST documentados (OpenAPI).
- **Reasignación a agente específico:** asignar ticket a un agente dentro del sector.
- **Vista de historial de auditoría** por ticket (línea de tiempo de `historial_ticket`). **[v2]**

---

## Etapa 10 — Criterios de aceptación (Definition of Done)

Para considerar la v1 terminada, la IA debe entregar:

1. **Etapa 1 cumplida:** arquitectura/stack propuestos y **aprobados antes de codificar**.
2. Proyecto que **corre localmente** con un `README` (install + run).
3. `seed`/config que crea los sectores (D-05) y reconoce a `ti@13dejulio.edu.ar`
   como superadmin (`SUPERADMIN_EMAILS`).
4. Todas las casillas de la Etapa 8 marcadas y funcionales de punta a punta.
5. Login Google **solo** para `@13dejulio.edu.ar`, con **verificación del ID
   token** y rechazo verificado para otros dominios (incluir prueba). **[v2]**
6. **Pruebas automatizadas** de los flujos críticos (RN-11): login/rechazo de
   dominio, crear, comentar según alcance, cambiar estado (transición válida e
   **inválida rechazada**), cambiar prioridad, derivar, reasignar, **cerrar solo
   desde `resuelto`**, reabrir. Un **CI mínimo** que las ejecute. **[v2]**
7. La máquina de estados (Etapa 6) respetada en backend y UI; transiciones
   inválidas rechazadas en el backend.
8. **Autorización por rol y alcance** (matriz Etapa 5) aplicada en cada
   endpoint/pantalla. **[v2]**
9. **Auditoría** funcionando: cada cambio de estado/prioridad/sector en
   `historial_ticket` y cada cambio de rol en `historial_rol`. **[v2]**
10. **Invariantes de gobernanza (RF-17):** nunca sin directivos; superadmin no
    degradable por no-superadmin. **[v2]**
11. **Guarda de baja de sector (RF-16):** no se puede desactivar un sector con
    tickets abiertos. **[v2]**
12. Sin credenciales ni secretos hardcodeados (variables de entorno, incluidas
    las del OAuth de Google provistas por el usuario).
13. La lista de sectores efectivamente configurable (no constante en código).

---

## Etapa 11 — Mejoras futuras

Ver Etapa 9. Además: Postgres compartido con otros sistemas de la organización
(a evaluar por separado), reportería avanzada, y SLA/notificaciones.

---

## Anexo — Instrucciones para la IA implementadora

- **No inicies el desarrollo sin la aprobación de la Etapa 1.**
- Las **decisiones de la Etapa 0.5 son definitivas**: no las re-propongas.
- Autenticación: **Google OAuth 2.0 restringido a `13dejulio.edu.ar`**, con
  **verificación del ID token** (firma, `aud`, `iss`, `exp`, `email_verified`) y
  `hd` preferente; sin passwords locales. La OAuth App la gestiona el usuario en
  Google Cloud Console; la IA solo consume credenciales por variables de entorno
  (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, redirect URI, `SUPERADMIN_EMAILS`).
- **Superadmin inicial:** `ti@13dejulio.edu.ar` (configurable vía `SUPERADMIN_EMAILS`).
- Stack libre (web full-stack) salvo lo anterior; elegí tecnologías maduras y
  **el mismo motor de base en dev y prod**. **[v2]**
- Seguí la **semántica** del modelo de datos (Etapa 4); los nombres son guía,
  pero respetá la relación **N–N** agente↔sector y el **historial unificado**.
- Aplicá **autorización por rol y alcance** (matriz Etapa 5) en backend y UI.
- Entregá código modular, con separación clara entre datos, lógica y vista, y
  **pruebas automatizadas** de los flujos críticos (Etapa 10.6).
- Respetá estrictamente los roles (Etapa 5) y la máquina de estados (Etapa 6),
  rechazando transiciones inválidas en el backend.
- Los sectores deben ser **datos configurables**, no constantes del código.

---

### Apéndice — Decisiones asumidas que el usuario puede revertir **[Asumido v2]**

Estas se aplicaron con un default estándar; confirmá o corregí:

- **C-05** Verificación del ID token + `email_verified` + `hd` preferente.
- **C-06** `historial_ticket` unificado (estado/prioridad/sector) en lugar de `Derivacion`.
- **C-07** Gobernanza de roles (auditoría + nunca sin directivos + superadmin no degradable).
- **C-08** Matriz de permisos por rol y alcance (Etapa 5).
- **Etapa 1 §5** Mismo motor de base en dev y prod.
