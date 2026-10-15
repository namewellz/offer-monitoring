-- Simulacao de backfill usada para gerar sample_display.txt (scratch DB apenas)
UPDATE stores s SET neighborhood=v.b, store_code=v.c, field_sources=field_sources||jsonb_build_object('neighborhood',v.src)
FROM (VALUES
 ('Atacadão Campinas Jd. Yeda','Jardim Yeda','662','app=viacep'),
 ('Atacadão Campinas Dom Pedro','Jardim Santa Genebra','663','app=viacep'),
 ('Atacadão Campinas Dunlop 24h','Jardim Aurélia','677','app=viacep'),
 ('Atacadão Hortolândia','Parque São Miguel','632','app=viacep'),
 ('Atacadão Americana','Vila Bertini','625','app (viacep: São Vito)'),
 ('Atacadão Indaiatuba','Recreio Campestre Joia','658','app (viacep: Itaici)'),
 ('Atacadão Itu','Brasil','816','app (viacep: São Luiz)'),
 ('Atacadão Jundiaí','Jardim Liberdade','633','app=viacep'),
 ('Atacadão Santa Bárbara d''Oeste','Loteamento Industrial','948','app=viacep'),
 ('Atacadão Sumaré','Chácara Monte Alegre','736','app=viacep'),
 ('Atacadão Vila Maria','Vila Maria','60','manual'),
 ('Spani Campinas 1','Alphaville Dom Pedro','CD40','viacep'),
 ('Spani Campinas 2','Parque Universitário de Viracopos','CD41','viacep'),
 ('Spani Campinas 3','Jardim Paulicéia','CD42','viacep'),
 ('Taquaral (Campinas)','Taquaral','1','viacep'),
 ('Hortolândia - Hortolândia - LJ 55','Vila São Francisco','55','viacep'),
 ('Pague Menos Hortolândia (Loja 16 - Rosolen)',NULL,'16','gap'),
 ('Assaí Hortolândia – Loja 175',NULL,'175','gap'),
 ('Loja 04 – Monte Mor',NULL,'04','gap'),
 ('GoodBom Hortolândia',NULL,'hortolandia','gap'),
 ('GoodBom Monte Mor',NULL,'monte-mor','gap'),
 ('Max Atacadista Campinas',NULL,'141','gap'),
 ('São Vicente Hortolândia',NULL,'018','gap'),
 ('Tenda Hortolândia',NULL,'CT39','gap')
) v(n,b,c,src) WHERE s.name=v.n;
UPDATE stores SET display_label='Dunlop 24h' WHERE name='Atacadão Campinas Dunlop 24h';
UPDATE stores SET display_label='Dom Pedro' WHERE name='Atacadão Campinas Dom Pedro';
UPDATE stores SET display_label='Jd. Yeda' WHERE name='Atacadão Campinas Jd. Yeda';
