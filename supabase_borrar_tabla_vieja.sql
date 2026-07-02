-- Ejecutar esto en el SQL Editor de Supabase (una sola vez).
-- Borra la tabla de prueba "resultados_encuesta" (la evaluación cognitiva
-- de Encuesta.txt) junto con sus 30 filas y sus policies. Esto es
-- IRREVERSIBLE. Después de correr esto, en el proyecto van a quedar
-- solo las tablas "usuarios" y "encuesta_comidas".

drop table if exists resultados_encuesta;
