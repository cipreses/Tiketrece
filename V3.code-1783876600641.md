# Propuesta Etapa 1: Sistema de Tickets de Servicios (Revisada v3)

## 1. Arquitectura
Propongo un **Monolito Web (Server-Side Rendering)**[cite: 2].
Toda la lógica de negocio, acceso a datos y generación de vistas conviven en la misma base de código.
**Justificación:** Al ser una herramienta interna para la organización[cite: 1], separar el frontend del backend suma complejidad innecesaria. Un monolito nos permite iterar rápido y facilita el mantenimiento a largo plazo[cite: 2].

## 2. Entorno de Desarrollo
*   **Sistema Operativo:** Entornos Linux[cite: 2].
*   **Runtime/Herramientas:** Python 3.11+ con entornos virtuales (`venv`)[cite: 2].
*   **Gestor de paquetes:** `pip`[cite: 2].

## 3. Lenguajes
*   **Backend:** Python[cite: 2].
*   **Frontend:** HTML5, CSS3, JavaScript mínimo[cite: 2].

## 4. Frameworks y librerías clave
*   **Backend:** **Django**[cite: 2].
    *   *Justificación:* Su ORM resuelve nativamente la relación N-N (`usuario_sector`)[cite: 1, 2]. 
    *   *Aclaración sobre el Admin:* Usaremos el Panel de Administración de Django para gestionar sectores y roles, pero **no directamente**. Implementaremos `ModelForms` personalizados y sobreescribiremos los métodos `clean()` para garantizar por código el RF-16 (guarda de baja de sector) y el RF-17 (invariantes de gobernanza)[cite: 1, 2]. No se expondrá todo el Admin; los directivos tendrán permisos (`is_staff`) acotados estrictamente a esos modelos[cite: 1, 2].
*   **Frontend interactivo:** **HTMX**[cite: 2].
*   **Autenticación:** Librería `google-auth` para la validación criptográfica de los tokens OAuth[cite: 2].

## 5. Base de Datos y Modelo de Auditoría
*   **Motor:** **PostgreSQL** tanto en desarrollo como en producción[cite: 1, 2].
*   **Migraciones:** Gestionadas por Django[cite: 2].
*   **Historial Unificado (RF-15 y RF-17):** Modelaremos `historial_ticket` e `historial_rol` como tablas estrictamente *append-only*[cite: 1]. En lugar de depender de Signals (que no capturan fácilmente el `request.user` ni atajan los updates masivos), implementaremos el patrón de **Capa de Servicios**[cite: 2]. Las vistas llamarán a funciones de negocio (ej. `ticket_service.cambiar_estado(ticket, nuevo_estado, actor)`) que se encargarán de actualizar el registro principal y escribir el historial de forma atómica dentro de un bloque `transaction.atomic()`, asegurando que el actor siempre quede registrado y no se pierdan trazas[cite: 1].

## 6. Autenticación (Implementación Endurecida)
Nos integramos con Google OAuth 2.0 (OpenID Connect)[cite: 1, 2].
*   **Flujo y CSRF:** Implementaremos el flujo Authorization Code generando y validando un parámetro `state` para prevenir ataques CSRF[cite: 1, 2].
*   **Verificación del ID Token:** Se validará la firma, el `aud` contra el `GOOGLE_CLIENT_ID`, la expiración (`exp`), que `email_verified == true`, y exigiremos explícitamente que el claim `iss` sea válido (`accounts.google.com` o `https://accounts.google.com`)[cite: 1, 2].
*   **Restricción de dominio:** Si el claim `hd` (o el dominio del email) no es exactamente `13dejulio.edu.ar`, se rechaza el inicio de sesión y no se crea el usuario[cite: 1, 2].
*   **Sesión:** El `google_sub` será la clave de identidad[cite: 1]. La sesión se manejará en el backend vía cookies firmadas por Django[cite: 1, 2].
*   **Variables:** Las credenciales y configuraciones se inyectarán por variables de entorno (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SUPERADMIN_EMAILS`, etc.)[cite: 1, 2].

## 7. Autorización (Rol + Alcance)
*   **Filtros de Vista:** A nivel ORM, generaremos querysets dinámicos para que el directivo tenga alcance global, el agente vea tickets de sus sectores y el solicitante solo los propios[cite: 1, 2].
*   **Guards en Acciones:** Decoradores customizados en cada endpoint verificarán la matriz de permisos de la Etapa 5 antes de ejecutar acciones como derivar o cambiar prioridad[cite: 1, 2].

## 8. Pruebas y CI
*   **Framework:** `pytest` con `pytest-django`[cite: 2].
*   **Flujos críticos a cubrir:**
    *   **Alcance y Visibilidad:** Verificar que un solicitante solo pueda ver sus propios tickets, y que un agente solo vea los del sector que tiene asignado[cite: 1, 2].
    *   **Autorización de Acciones:** Asegurar que un agente no pueda cambiar el estado, derivar o modificar tickets que no pertenezcan a su sector[cite: 1, 2].
    *   **Regla "Relacionado" (RF-10):** Probar que los solicitantes solo puedan comentar en sus tickets, y los agentes/directivos en los correspondientes a su alcance[cite: 1].
    *   Login exitoso y rechazo explícito por dominio distinto a `13dejulio.edu.ar`[cite: 1, 2].
    *   Transiciones de la máquina de estados, validando que se rechacen los saltos inválidos[cite: 1, 2].
    *   **Prueba del RF-16:** Intentar desactivar un sector con tickets abiertos y corroborar el rechazo[cite: 1, 2].
    *   **Pruebas del RF-17:** Verificar que no se pueda eliminar al último directivo y que un agente/directivo común no pueda degradar al superadmin[cite: 1, 2].
    *   Verificación de que toda la capa de servicios escriba correctamente en las tablas append-only de auditoría con el actor correspondiente[cite: 1].
*   **CI:** Pipeline automatizado que corra linters y la suite de tests en cada push[cite: 1, 2].

## 9. Despliegue Objetivo
*   **Producción:** Servidor con contenedores orquestados vía **Podman** (o Docker)[cite: 1, 2].
*   **Componentes:** App (Django + WSGI), PostgreSQL y un proxy inverso[cite: 2]. 

## 10. Estructura del Repositorio
*   `/config/`: Settings globales y enrutamiento[cite: 2].
*   `/apps/`: Lógica dividida por dominio (`usuarios`, `sectores`, `tickets`)[cite: 2].
*   `/tests/`: Pruebas automatizadas de flujos críticos[cite: 2].

## 11. Tabla Comparativa
| Característica | Opción Principal: Django (Monolito) | Alternativa: Node.js (NestJS) + React |
| :--- | :--- | :--- |
| **Ajuste a la spec** | Excelente. El ORM maneja perfecto la tabla puente N-N de usuarios y sectores[cite: 1, 2]. | Bueno, pero requiere configurar un ORM externo como Prisma o TypeORM[cite: 2]. |
| **CRUD inicial (RF-16, RF-17)** | Usamos el Admin de Django, pero sumando validaciones customizadas (`clean()`) para garantizar la gobernanza de roles y la guarda de baja de sector[cite: 1, 2]. | Hay que construir todas las pantallas de ABM y las validaciones de backend/frontend desde cero[cite: 2]. |
| **Auditoría (historial)** | La capa de servicios permite interceptar cambios, registrar al actor y escribir el historial *append-only* en la misma transacción[cite: 1, 2]. | Requiere armar servicios y transacciones manuales similares en TypeORM[cite: 2]. |
| **Simplicidad operativa** | Alta. Un solo lenguaje y repositorio[cite: 2]. | Baja. Mantener 2 repos, doble stack y gestionar API REST / CORS[cite: 2]. |

## 12. Qué falta para arrancar
1. **Aprobar el GATE:** Confirmar si avanzamos con esta arquitectura[cite: 1, 2].
2. **Credenciales:** Configurar la OAuth App en Google Cloud Console para obtener el `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET`[cite: 1, 2].