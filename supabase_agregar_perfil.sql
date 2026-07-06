-- Ejecutar esto en el SQL Editor de Supabase (una sola vez).
-- Agrega las columnas de "Mi perfil" a la tabla usuarios que ya existe.
-- No borra ni modifica ningún dato existente.

alter table usuarios add column if not exists nombre text;
alter table usuarios add column if not exists edad integer;
alter table usuarios add column if not exists educacion text;
alter table usuarios add column if not exists ocupacion text;
