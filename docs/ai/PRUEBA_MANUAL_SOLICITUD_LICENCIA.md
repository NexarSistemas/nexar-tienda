## Prueba manual: solicitud de licencia a Supabase

1. Configurar `SUPABASE_URL` con la URL base del proyecto, por ejemplo:
   `https://tu-proyecto.supabase.co`
2. Configurar `SUPABASE_ANON_KEY` con la anon key publica.
3. Abrir Nexar Tienda.
4. Ir a `/licencia`.
5. Completar el formulario de solicitud de licencia.
6. Enviar la solicitud.
7. Verificar en Supabase que se inserte un registro en la tabla `solicitudes_licencia`.

URL REST final esperada:
`https://tu-proyecto.supabase.co/rest/v1/solicitudes_licencia`
