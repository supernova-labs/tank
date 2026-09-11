# Referência dos checks do `tank check`

Todo achado do relatório carrega um **código estável** (esta página) e um **estado**. Um relatório vale somente para o ambiente que ele nomeia no cabeçalho (servidor, versão, `ns`/`db`).

## Os estados

| Estado | Significado |
|---|---|
| `PASS` | A declaração **não é contradita** pelo schema e pela amostra deste ambiente. Não é prova de correção semântica — veja a seção "Não verificado" do relatório. |
| `FAIL` | O banco contradiz a declaração. Quebra o build (exit 1). |
| `WARN` | Suspeito ou frágil, mas não contraditório. Não quebra o build — salvo com `--strict`. |
| `VACUOUS` | O check amostral não pôde provar nada porque **a tabela está vazia**. Nunca é convertido em PASS silencioso — tabela vazia não é evidência. `--strict` o trata como falha. |
| `INFO` | Informativo, sem veredito. |

**Exit codes do CLI**: `0` = sem FAIL · `1` = há FAIL (ou WARN/VACUOUS com `--strict`) · `2` = erro de uso, conexão ou **ontologia internamente inválida** (os `ONT-*` abaixo).

---

## `ONT-*` — consistência interna da ontologia (estáticos, sem banco)

Rodam **no construtor da `Ontology`**, em qualquer import. Falha = `OntologyError` com **todas** as violações de uma vez — o build quebra antes de existir conexão. Erros de *forma* de um campo isolado (métrica inexistente, `dim=0`, `values=[]`, `field_link` sem `field`) chegam como `ValidationError` do Pydantic, apontando a linha exata.

| Código | O que verifica | Como consertar |
|---|---|---|
| `ONT-001` | Nomes únicos de tipos, relações e escopos | Renomeie o duplicado |
| `ONT-002` | `Relation.from_`/`to` referenciam tipos declarados | Declare o tipo faltante ou corrija o nome |
| `ONT-003` | `Scope.via` referencia uma relação declarada | Declare a relação ou corrija o nome |
| `ONT-005` | Attrs sem duplicata dentro do mesmo tipo | Remova a duplicata |
| `ONT-008` | `Freshness.unit_type` referencia um tipo declarado | Corrija o nome do tipo |
| `ONT-009` | Campo de `field_link` não colide com attr de tipo não-record no tipo de origem | Ajuste o attr para `record` ou renomeie |

## `TBL-*` / `VAC-*` — tabelas

| Código | O que verifica | Estados possíveis |
|---|---|---|
| `TBL-000` | O nome da tabela é um identificador simples (`[A-Za-z_][A-Za-z0-9_]*`) | FAIL |
| `TBL-001` | **A tabela declarada em `UnitType.table` existe no banco.** O erro canônico: "você está me dando uma ontologia que não existe no banco". A mensagem PASS informa `SCHEMAFULL/SCHEMALESS` e o `kind` | PASS / FAIL |
| `VAC-001` | Tabela de tipo declarado com **0 linhas** → todos os checks amostrais do tipo são vácuos | VACUOUS |

## `FLD-*` / `ATTR-*` — campos e vocabulários

A dicotomia real é **por campo** (comportamento verificado no SurrealDB 2.x e 3.x): campo com `DEFINE FIELD` é validado estruturalmente — e o próprio SurrealDB o defende no write, até em tabela SCHEMALESS. Campo sem `DEFINE` não é defendido por ninguém → só amostragem.

| Código | O que verifica | Estados possíveis |
|---|---|---|
| `FLD-000` | Nome de campo é identificador simples | FAIL |
| `FLD-001` | Campo referenciado pela declaração (`text`, `attrs`, `locator`, `id`, `vector.field`, `fulltext.field`) tem `DEFINE FIELD` na tabela; para attrs, o tipo da DDL é compatível com o declarado | PASS |
| `FLD-002` | Campo **sem** `DEFINE FIELD`: presença verificada por amostragem. Ausente em 100% da amostra = FAIL; parcial = WARN; presente em tudo = PASS com a recomendação de criar o `DEFINE` | PASS / WARN / FAIL |
| `FLD-003` | Tipo declarado no `Attr` diverge do tipo da DDL (ex.: attr `string`, DDL `int`) | WARN |
| `ATTR-010` | Valores amostrados do campo cabem no vocabulário `Attr.values` declarado | PASS / WARN |

## `REL-*` — relações

| Código | O que verifica | Estados possíveis |
|---|---|---|
| `REL-001` | **A tabela da aresta existe** ("relation declara tabela X, que não existe no banco") | PASS implícito via REL-002 / FAIL |
| `REL-002` | Direção da aresta. Com `TYPE RELATION IN/OUT`: comparação estrutural — e o servidor **impõe a direção no write**. Com `TYPE ANY` (aresta criada só por `RELATE`): amostragem de `record::tb(in/out)` — endpoints certos = WARN recomendando explicitar `TYPE RELATION`; errados = FAIL; vazia = VACUOUS | PASS / WARN / FAIL / VACUOUS |
| `REL-003` | `field_link`: o campo no tipo de origem existe e é `record<tabela-destino>` | PASS / WARN / FAIL / VACUOUS |
| `REL-004` | O campo de `Weight` existe na aresta (DEFINE ou amostragem) | PASS / WARN / FAIL / VACUOUS |

## `VEC-*` — busca vetorial

A ontologia declara a *capacidade* (`Vector(field, dim, metric)`); o índice é **derivado** da declaração — nunca declarado diretamente.

| Código | O que verifica | Estados possíveis |
|---|---|---|
| `VEC-001` | Existe índice ANN (HNSW/MTREE/DISKANN) cobrindo o campo declarado. Sem ele, busca vetorial vira full scan ou erro | PASS implícito / FAIL |
| `VEC-002` | `DIMENSION` do índice == `dim` declarado | PASS / FAIL |
| `VEC-003` | `DIST` do índice == `metric` declarada | PASS / FAIL |
| `VEC-004` | Índice é MTREE — deprecado em 2.x, removido em 3.x | WARN |
| `VEC-010` | Dimensão dos embeddings **amostrados** == `dim`. Pega linhas ingeridas *antes* do índice existir (com índice presente, o servidor rejeita dimensão errada no write; sem ele, dimensões mistas se acumulam em silêncio — um modo de falha real de produção) | PASS / FAIL |

## `FTS-*` — busca full-text

| Código | O que verifica | Estados possíveis |
|---|---|---|
| `FTS-001` | Existe índice FTS (`FULLTEXT ANALYZER` no 3.x / `SEARCH ANALYZER` no 2.x) cobrindo o campo declarado | PASS / FAIL |
| `FTS-002` | O analyzer do índice é o declarado, e está definido no banco | FAIL |
| `FTS-003` | A `language` declarada é coberta pelo `snowball(...)` do analyzer | WARN |

## `FRS-*` — freshness

| Código | O que verifica | Estados possíveis |
|---|---|---|
| `FRS-001` | O campo de `Freshness` está entre os campos declarados do tipo (e portanto validado pelos FLD) | PASS / WARN |

---

## O que o `tank check` deliberadamente NÃO verifica

Impressa em todo relatório, a lista de honestidade: semântica dos nomes, identidade real do modelo de embedding (só o rótulo declarado no 0.1), qualidade/completude do conteúdo, comportamento de busca/ranking (nenhuma query de acesso é executada) e direção *semântica* das relações (estrutura ≠ significado). Um doctor que silencia sobre o que não checou fabrica confiança falsa.
