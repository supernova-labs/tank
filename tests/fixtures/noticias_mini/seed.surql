-- noticias_mini: a complete news-graph fixture — 4 typed tables, 3 TYPE RELATION
-- edges, vector + fulltext on noticia. Exercises every connected check family.
DEFINE ANALYZER az_pt TOKENIZERS blank FILTERS lowercase, snowball(portuguese);

DEFINE TABLE noticia SCHEMAFULL;
DEFINE FIELD titulo       ON noticia TYPE string;
DEFINE FIELD corpo        ON noticia TYPE string;
DEFINE FIELD publicado_em ON noticia TYPE datetime;
DEFINE FIELD emb          ON noticia TYPE option<array<float>>;
DEFINE INDEX idx_fts ON noticia FIELDS corpo FULLTEXT ANALYZER az_pt BM25 HIGHLIGHTS;
DEFINE INDEX idx_vec ON noticia FIELDS emb HNSW DIMENSION 4 DIST COSINE;

DEFINE TABLE entidade SCHEMAFULL;
DEFINE FIELD nome ON entidade TYPE string;
DEFINE FIELD tipo ON entidade TYPE string ASSERT $value IN ['pessoa', 'orgao', 'organizacao'];

DEFINE TABLE tema SCHEMAFULL;
DEFINE FIELD nome ON tema TYPE string;

DEFINE TABLE documento SCHEMAFULL;
DEFINE FIELD numero ON documento TYPE string;
DEFINE FIELD estado ON documento TYPE string ASSERT $value IN ['tramitando', 'aprovado', 'rejeitado'];

DEFINE TABLE fala_de TYPE RELATION IN noticia OUT entidade SCHEMAFULL;
DEFINE FIELD peso ON fala_de TYPE float;
DEFINE TABLE sobre TYPE RELATION IN noticia OUT tema SCHEMAFULL;
DEFINE TABLE cita TYPE RELATION IN noticia OUT documento SCHEMAFULL;

CREATE entidade:e1 SET nome='Entidade Alfa', tipo='pessoa';
CREATE entidade:e2 SET nome='Orgao Beta', tipo='orgao';
CREATE tema:t1 SET nome='Tema Um';
CREATE tema:t2 SET nome='Tema Dois';
CREATE documento:d1 SET numero='DOC-001/2026', estado='tramitando';
CREATE documento:d2 SET numero='DOC-002/2026', estado='aprovado';

CREATE noticia:n1 SET titulo='Noticia um', corpo='Texto da noticia um sobre o tema.', publicado_em=d'2026-09-01T10:00:00Z', emb=[0.1, 0.2, 0.3, 0.4];
CREATE noticia:n2 SET titulo='Noticia dois', corpo='Texto da noticia dois citando documento.', publicado_em=d'2026-08-15T10:00:00Z', emb=[0.4, 0.3, 0.2, 0.1];
CREATE noticia:n3 SET titulo='Noticia tres', corpo='Texto da noticia tres.', publicado_em=d'2026-07-01T10:00:00Z', emb=[0.2, 0.2, 0.2, 0.2];

RELATE noticia:n1->fala_de->entidade:e1 SET peso=0.9;
RELATE noticia:n1->fala_de->entidade:e2 SET peso=0.4;
RELATE noticia:n2->fala_de->entidade:e1 SET peso=0.7;
RELATE noticia:n1->sobre->tema:t1;
RELATE noticia:n2->sobre->tema:t2;
RELATE noticia:n2->cita->documento:d1;
RELATE noticia:n3->cita->documento:d2;
