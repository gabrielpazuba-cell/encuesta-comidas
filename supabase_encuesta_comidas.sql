-- Ejecutar esto en el SQL Editor de Supabase (una sola vez).
-- Tabla PROPIA para la encuesta de comidas, separada de "resultados_encuesta"
-- (esa otra tabla es de la evaluación cognitiva semanal, no tocar).

create table if not exists encuesta_comidas (
    id bigint generated always as identity primary key,
    usuario text not null,              -- email de quien respondió
    fecha timestamp not null,           -- hora local en que se dio esa respuesta
    momento_dia text not null,          -- "Desayuno" | "Almuerzo" | "Merienda" | "Cena"
    hora_consumo text,                  -- "HH:MM" (null si respondió "No tuve")
    item_nombre text,                   -- nombre de la comida/bebida cargada
    item_categoria text,                -- "Comida" | "Bebida"
    item_detalle text,                  -- opción elegida en el desplegable de detalle
    item_tamano text,                   -- tamaño de porción elegido
    tipo_registro text not null default 'item',  -- 'comida_hora' | 'item'
    tuvo_comida boolean,                -- si respondió que sí tuvo esa comida
    tiempo_respuesta_seg numeric,       -- segundos que tardó en responder
    created_at timestamptz not null default now()
);

-- La app usa la clave pública (anon), así que necesita permiso para
-- leer/escribir en esta tabla.
alter table encuesta_comidas enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where tablename = 'encuesta_comidas' and policyname = 'encuesta_comidas_select'
    ) then
        create policy "encuesta_comidas_select" on encuesta_comidas for select using (true);
    end if;

    if not exists (
        select 1 from pg_policies
        where tablename = 'encuesta_comidas' and policyname = 'encuesta_comidas_insert'
    ) then
        create policy "encuesta_comidas_insert" on encuesta_comidas for insert with check (true);
    end if;
end $$;
