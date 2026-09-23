# B2b — resolução índice → campo

O passo do matcher que o B2 deixou **inteiramente sem medição**: quando a
query usa índice, o plano devolve só o NOME do índice. Dá para recuperar o
campo? Fixture: `tests/fixtures/news_mini` + índices standard/composto/unique.

Mapa construído pelo `Introspector` + `parse_index_ddl` do repo: **6 índices, zero código de parsing novo**.

| caso | operador | índice usado | campo resolvido | campo no texto do plano? | verdade |
|---|---|---|---|---|---|
| mesma query, SEM índice (WITH NOINDEX) | `TableScan` | — | — | sim | `title` |
| mesma query, COM índice | `IndexScan` | `idx_title` | `title` | **não** | `title` |
| campo sem índice nenhum | `TableScan` | — | — | sim | `status` |
| range em campo indexado | `IndexScan` | `idx_pub` | `published_at` | **não** | `published_at` |
| composto, prefixo completo (kind+name) | `IndexScan` | `idx_ent_kind` | `kind`, `name` | **não** | `kind` |
| composto, só o prefixo (kind) | `IndexScan` | `idx_ent_kind` | `kind`, `name` ⚠ só 1 usado(s) | **não** | `kind` |
| composto, só o SEGUNDO campo (name) | `TableScan` | — | — | sim | `name` |
| unique | `IndexScan` | `idx_doc_num` | `number` | **não** | `number` |
| full-text | `FullTextScan` | `idx_fts` | `body` | **não** | `body` |
| vetorial (KNN) | `KnnScan` | `idx_vec` | `emb` | **não** | `emb` |
| travessia de grafo | `TableScan` | — | — | sim | `out` |

**7 casos usaram índice.** Em **7** deles o campo desapareceu do texto do plano; o mapa recuperou **7**.

- **mesma query, SEM índice (WITH NOINDEX)** → {'projection': ['id'], 'filter': ["title = 'Quantum leap'"]}
- **mesma query, COM índice** → {'projection': ['id'], 'filter': ["= 'Quantum leap'"]}
- **campo sem índice nenhum** → {'projection': ['id'], 'filter': ["status = 'approved'"]}
- **range em campo indexado** → {'projection': ['id'], 'filter': [">d'2020-01-01T00:00:00Z'"]}
- **composto, prefixo completo (kind+name)** → {'projection': ['id'], 'filter': ["['person', 'Ada']"]}
- **composto, só o prefixo (kind)** → {'projection': ['id'], 'filter': ["['person']"]}
- **composto, só o SEGUNDO campo (name)** → {'projection': ['id'], 'filter': ["name = 'Ada'"]}
- **unique** → {'projection': ['id'], 'filter': ["= 'PL-1'"]}
- **full-text** → {'projection': ['id'], 'fulltext': ['quantum']}
- **vetorial (KNN)** → {'projection': ['id']}
- **travessia de grafo** → {'projection': ['id'], 'filter': ['out = entity:e1']}

---

## O que isto fecha

**A assimetria é real, e a demonstração é a mesma query duas vezes:**

```
SELECT id FROM news WITH NOINDEX WHERE title = 'x'   →  filter: "title = 'x'"   ← campo presente
SELECT id FROM news              WHERE title = 'x'   →  filter: "= 'x'"         ← campo sumiu
```

Sem resolução, **ligar um índice faria um attr parar de ser observável** — o instrumento
ficaria mais quieto exatamente quando o banco fica mais bem afinado. É o pior modo de falha
possível para um dinamômetro.

**A resolução funciona, e sem código novo.** O `Introspector` + `parse_index_ddl` que já estão
no 0.1 devolvem `{índice: (tabela, campos ordenados, kind)}` para os seis índices da fixture —
inclusive FULLTEXT e HNSW. **7 de 7** casos indexados recuperados. A afirmação do plano ("zero
código novo de parsing") se sustenta.

## Três regras que esta bancada obriga no matcher

1. **Índice composto exige contar a aridade, senão super-reporta.** `idx_ent_kind` cobre
   `kind, name`. Numa query que filtra só por `kind`, o mapa devolve os DOIS campos — e reportar
   `name` como usado é "observado-presente" mentindo. O plano desambigua: o slot `access` traz
   **um valor por campo efetivamente ligado** — `['person']` (só o prefixo) × `['person','Ada']`
   (os dois). **Regra: resolver no máximo os N primeiros campos do índice, onde N = número de
   valores em `access`.**
2. **KNN não traz slot de filtro nenhum** — o plano do `<|K,EF|>` é só `{'projection': ['id']}`.
   O nome do índice é o único sinal, e o mapa recupera o campo (`emb`), mas **não existe valor
   nem operador**. Limite honesto: para query vetorial o 3a sabe *que campo*, nunca *com o quê*.
3. **Cache desatualizado falha como MISS, não como resposta errada.** Índice criado depois do
   bootstrap não está no mapa e resolve para `None` — detectável. Confirma a prescrição do plano:
   miss ⇒ um refresh; se persistir ⇒ `unobserved += ["plan.indexes"]` com razão `unknown_index`,
   e **nunca** bloqueia a chamada.

## Dois bugs da própria bancada, registrados

- O mapa voltou **vazio** na primeira rodada e eu quase reportei que o `Introspector` não serve.
  Era a bancada semeando no namespace `b2` e lendo do `b2b` — o helper `sql()` lê o namespace do
  módulo onde mora. O `Introspector` estava certo o tempo todo.
- O primeiro caso ("scan, campo sem índice") era **a mesma query** do segundo, sobre um campo que
  eu mesmo tinha indexado na linha acima. Sem o contrafactual explícito (`WITH NOINDEX`) a tabela
  não provava nada.

Somando o `lit ×194` do B2, são **três** medições que teriam sido publicadas erradas se não
fossem conferidas contra o caso negativo. É o argumento a favor da bateria de sabotagem do plano
de testes: um número que ninguém tentou derrubar não vale como evidência.
