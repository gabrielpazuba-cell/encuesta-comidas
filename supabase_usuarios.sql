-- Ejecutar esto en el SQL Editor de Supabase (una sola vez)

create table if not exists usuarios (
    id uuid primary key default gen_random_uuid(),
    email text unique not null,
    sesiones_historicas integer not null default 0,
    ultima_fecha_completado date,
    created_at timestamptz not null default now()
);

alter table usuarios enable row level security;

-- La app usa la clave pública (anon), así que necesita permiso para
-- leer/crear/actualizar filas de esta tabla.
create policy "usuarios_select" on usuarios for select using (true);
create policy "usuarios_insert" on usuarios for insert with check (true);
create policy "usuarios_update" on usuarios for update using (true) with check (true);
