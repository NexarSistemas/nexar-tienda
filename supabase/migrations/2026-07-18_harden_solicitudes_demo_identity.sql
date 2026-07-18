-- Refuerzo idempotente para solicitudes DEMO de Nexar Comercio.
--
-- Proposito:
--   Permitir que Nexar Admin/Licencias deduplique altas DEMO por producto e
--   identidad fuerte sin depender de campos editables del cliente ni del email.
--
-- Tabla afectada:
--   public.solicitudes_demo
--
-- Rollback:
--   DROP INDEX IF EXISTS idx_solicitudes_demo_producto_identity_hash_unique;
--   DROP INDEX IF EXISTS idx_solicitudes_demo_producto_activation_id;
--   DROP INDEX IF EXISTS idx_solicitudes_demo_producto_hardware_id_hash;
--   ALTER TABLE public.solicitudes_demo DROP COLUMN IF EXISTS identity_hash;
--   ALTER TABLE public.solicitudes_demo DROP COLUMN IF EXISTS activation_id;
--   ALTER TABLE public.solicitudes_demo DROP COLUMN IF EXISTS hardware_id_hash;
--   ALTER TABLE public.solicitudes_demo DROP COLUMN IF EXISTS machine_id_hash;

ALTER TABLE public.solicitudes_demo
    ADD COLUMN IF NOT EXISTS activation_id text,
    ADD COLUMN IF NOT EXISTS hardware_id_hash text,
    ADD COLUMN IF NOT EXISTS machine_id_hash text,
    ADD COLUMN IF NOT EXISTS identity_hash text;

CREATE INDEX IF NOT EXISTS idx_solicitudes_demo_producto_activation_id
    ON public.solicitudes_demo (producto, activation_id)
    WHERE activation_id IS NOT NULL AND btrim(activation_id) <> '';

CREATE INDEX IF NOT EXISTS idx_solicitudes_demo_producto_hardware_id_hash
    ON public.solicitudes_demo (producto, hardware_id_hash)
    WHERE hardware_id_hash IS NOT NULL AND btrim(hardware_id_hash) <> '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_solicitudes_demo_producto_identity_hash_unique
    ON public.solicitudes_demo (producto, identity_hash)
    WHERE identity_hash IS NOT NULL AND btrim(identity_hash) <> '';
