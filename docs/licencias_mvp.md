# Nexar Tienda — Licencias por token (MVP)

## Arquitectura propuesta

### Cliente (Nexar Tienda, Flask + pywebview)
- Pantalla `/licencia`:
  1. Captura datos de solicitud (nombre, email, negocio, equipo).
  2. Genera payload JSON para enviar a `licencias_fh`.
  3. Permite pegar token emitido.
  4. Valida y activa token localmente.
- API interna:
  - `POST /api/licencias/solicitud`
  - `POST /api/licencias/validar`
  - `POST /api/licencias/activar`
  - `GET /api/licencias/estado`

### Sistema de licencias (licencias_fh)
- Recibe payload de solicitud.
- Genera token firmado HS256 con claims mínimas:
  - `license_id`, `plan`, `nombre`, `email`
  - `machine_id` y/o `machine_hash`
  - `exp` (opcional)
- Entrega token al cliente por panel o email.

## Persistencia local (MVP)

Se guarda en tabla `config`:
- `license_token`, `license_tier`, `license_plan`
- `license_owner_name`, `license_owner_email`
- `license_machine_hash`, `license_activated_at`, `license_expires_at`

Esto permite funcionamiento offline para pywebview.

## Reutilización respecto a Nexar Almacén

Se reutiliza el patrón ya existente en Nexar (tabla `config` + validación de límites por tier):
- `database.py::TIER_LIMITS`
- `database.py::check_license_limits`
- Decoradores y flujo Flask ya presentes para control administrativo.

En vez de activar manualmente tier, ahora se activa por token firmado.

## MVP primero

- Validación local por HMAC (sin dependencia externa).
- Opcional: backend de licencias más adelante para revocación o auditoría.
- Compatible con pywebview porque todo ocurre sobre rutas Flask locales.
