-- Ejecutar esto en el SQL Editor de Supabase (una sola vez).
-- Agrega la columna donde se guarda el género que la persona elige al
-- completar su perfil ("Mujer", "Varón", "Otra opción no listada" o
-- "Prefiero no decir").
-- No borra ni modifica ningún dato existente.

alter table usuarios add column if not exists genero text;
