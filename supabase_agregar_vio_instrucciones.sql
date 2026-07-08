-- Ejecutar esto en el SQL Editor de Supabase (una sola vez).
-- Agrega la columna que recuerda si el usuario ya vio la pantalla de
-- instrucciones/video, para no mostrársela de nuevo en encuestas siguientes.
-- No borra ni modifica ningún dato existente.

alter table usuarios add column if not exists vio_instrucciones boolean not null default false;
