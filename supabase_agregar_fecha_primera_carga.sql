-- Ejecutar esto en el SQL Editor de Supabase (una sola vez).
-- Agrega la columna que guarda el día en que la persona completó su PRIMERA
-- carga. A partir de esa fecha se cuentan los 10 días que dura la
-- participación en el estudio.
-- No borra ni modifica ningún dato existente.

alter table usuarios add column if not exists fecha_primera_carga date;

-- Para los usuarios que ya venían participando antes de este cambio: se les
-- toma como primera carga el día en que se creó su cuenta, así no quedan sin
-- fecha de inicio. Solo afecta a quienes ya tienen alguna carga hecha.
update usuarios
   set fecha_primera_carga = created_at::date
 where fecha_primera_carga is null
   and sesiones_historicas > 0;
