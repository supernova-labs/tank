-- news_mini: a complete news-graph fixture — 4 typed tables, 3 TYPE RELATION
-- edges, one field_link (news.feed), vector + fulltext on news. Exercises every
-- connected check family.
DEFINE ANALYZER az_en TOKENIZERS blank FILTERS lowercase, snowball(english);

DEFINE TABLE feed SCHEMAFULL;
DEFINE FIELD name ON feed TYPE string;

DEFINE TABLE news SCHEMAFULL;
DEFINE FIELD title        ON news TYPE string;
DEFINE FIELD body         ON news TYPE string;
DEFINE FIELD published_at ON news TYPE datetime;
DEFINE FIELD emb          ON news TYPE option<array<float>>;
DEFINE FIELD feed         ON news TYPE record<feed>;
DEFINE INDEX idx_fts ON news FIELDS body FULLTEXT ANALYZER az_en BM25 HIGHLIGHTS;
DEFINE INDEX idx_vec ON news FIELDS emb HNSW DIMENSION 4 DIST COSINE;

DEFINE TABLE entity SCHEMAFULL;
DEFINE FIELD name ON entity TYPE string;
DEFINE FIELD kind ON entity TYPE string ASSERT $value IN ['person', 'agency', 'organization'];

DEFINE TABLE topic SCHEMAFULL;
DEFINE FIELD name ON topic TYPE string;

DEFINE TABLE document SCHEMAFULL;
DEFINE FIELD number ON document TYPE string;
DEFINE FIELD status ON document TYPE string ASSERT $value IN ['pending', 'approved', 'rejected'];

DEFINE TABLE mentions TYPE RELATION IN news OUT entity SCHEMAFULL;
DEFINE FIELD relevance ON mentions TYPE float;
DEFINE TABLE about TYPE RELATION IN news OUT topic SCHEMAFULL;
DEFINE TABLE cites TYPE RELATION IN news OUT document SCHEMAFULL;

CREATE feed:f1 SET name='Main wire';
CREATE entity:e1 SET name='Entity Alpha', kind='person';
CREATE entity:e2 SET name='Agency Beta', kind='agency';
CREATE topic:t1 SET name='Topic One';
CREATE topic:t2 SET name='Topic Two';
CREATE document:d1 SET number='DOC-001/2026', status='pending';
CREATE document:d2 SET number='DOC-002/2026', status='approved';

CREATE news:n1 SET title='News one', body='Body of news one about the topic.', published_at=d'2026-09-01T10:00:00Z', emb=[0.1, 0.2, 0.3, 0.4], feed=feed:f1;
CREATE news:n2 SET title='News two', body='Body of news two citing a document.', published_at=d'2026-08-15T10:00:00Z', emb=[0.4, 0.3, 0.2, 0.1], feed=feed:f1;
CREATE news:n3 SET title='News three', body='Body of news three.', published_at=d'2026-07-01T10:00:00Z', emb=[0.2, 0.2, 0.2, 0.2], feed=feed:f1;

RELATE news:n1->mentions->entity:e1 SET relevance=0.9;
RELATE news:n1->mentions->entity:e2 SET relevance=0.4;
RELATE news:n2->mentions->entity:e1 SET relevance=0.7;
RELATE news:n1->about->topic:t1;
RELATE news:n2->about->topic:t2;
RELATE news:n2->cites->document:d1;
RELATE news:n3->cites->document:d2;
