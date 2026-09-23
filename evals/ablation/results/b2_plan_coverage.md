# B2 — cobertura real do plano (degrau 3a)

Medido sobre as statements que os agentes da ablação realmente escreveram.
`ponderado` = por invocação real (tráfego); `distinto` = por forma de query.

## round1

Statements distintos: **185 de dado** (SELECT/RETURN) · 6 de introspecção · 0 outros. Tráfego de dado: 547/644 invocações (85%).

Tudo abaixo é **sobre as statements de dado** — introspecção não tem plano por construção e não conta contra a cobertura.

| observável | distinto | ponderado por tráfego |
|---|---|---|
| EXPLAIN devolveu plano | 184/185 (99%) | 546/547 (100%) |
| tem slot de filtro (predicate) | 139/185 (75%) | 440/547 (80%) |
| tem slot de ordenação (sort_keys) | 53/185 (29%) | 80/547 (15%) |
| tem projeção | 172/185 (93%) | 495/547 (90%) |
| resolveu ao menos 1 attr declarado | 115/185 (62%) | 406/547 (74%) |
| resolveu attr em papel de FILTRO | 84/185 (45%) | 339/547 (62%) |
| **elidiu algum slot** (arg de função) | 37/185 (20%) | 77/547 (14%) |
| **tem subquery** | 6/185 (3%) | 31/547 (6%) |
| nome não resolvido no vocabulário | 50/185 (27%) | 101/547 (18%) |
| usou índice | 0/185 (0%) | 0/547 (0%) |

**Plenamente observável** (plano ok, zero elisão, zero subquery, ao menos um attr resolvido): **91/185 (49%) distinto · 336/547 (61%) do tráfego**

Motivos de plano ausente: `{"code":400,"details":"Request problems detected","description":"There` ×1

Operadores vistos: `TableScan` ×175, `SelectProject` ×172, `SortByKey` ×32, `Limit` ×22, `SortTopKByKey` ×21, `RecordIdScan` ×6, `Project` ×6, `GraphEdgeScan` ×6

Attrs resolvidos por papel: projection ×128, filter ×87, sort ×31

Nomes não resolvidos (top 8): `article` ×27, `lowercase` ×13, `score` ×10, `seq` ×8, `position` ×6, `topics` ×5, `idx` ×3, `topic` ×2

## round2

Statements distintos: **485 de dado** (SELECT/RETURN) · 7 de introspecção · 0 outros. Tráfego de dado: 1073/1240 invocações (87%).

Tudo abaixo é **sobre as statements de dado** — introspecção não tem plano por construção e não conta contra a cobertura.

| observável | distinto | ponderado por tráfego |
|---|---|---|
| EXPLAIN devolveu plano | 459/485 (95%) | 1036/1073 (97%) |
| tem slot de filtro (predicate) | 294/485 (61%) | 672/1073 (63%) |
| tem slot de ordenação (sort_keys) | 61/485 (13%) | 112/1073 (10%) |
| tem projeção | 405/485 (84%) | 887/1073 (83%) |
| resolveu ao menos 1 attr declarado | 303/485 (62%) | 679/1073 (63%) |
| resolveu attr em papel de FILTRO | 227/485 (47%) | 526/1073 (49%) |
| **elidiu algum slot** (arg de função) | 45/485 (9%) | 111/1073 (10%) |
| **tem subquery** | 22/485 (5%) | 50/1073 (5%) |
| nome não resolvido no vocabulário | 92/485 (19%) | 187/1073 (17%) |
| usou índice | 0/485 (0%) | 0/1073 (0%) |

**Plenamente observável** (plano ok, zero elisão, zero subquery, ao menos um attr resolvido): **264/485 (54%) distinto · 602/1073 (56%) do tráfego**

Motivos de plano ausente: `{"code":400,"details":"Request problems detected","description":"There` ×26

Operadores vistos: `TableScan` ×443, `SelectProject` ×405, `SortByKey` ×40, `Aggregate` ×36, `Limit` ×30, `SortTopKByKey` ×21, `GraphEdgeScan` ×20, `CurrentValueSource` ×20

Attrs resolvidos por papel: projection ×482, filter ×246, sort ×43, computed ×4

Nomes não resolvidos (top 8): `seq` ×33, `topics` ×29, `lowercase` ×21, `article` ×20, `topic` ×15, `SelectProject` ×7, `passages` ×7, `title` ×6


---

## Como ler estes números

**Veredito:** o degrau 3a entrega **~55–60% do tráfego real plenamente observável** — plano
lido, zero elisão, zero subquery, ao menos um attr declarado resolvido. O resto não é perdido:
é *nomeado* (`elided`, `subquery`, `unknown_shape`), que é o que separa "não usou" de "não deu
para ver".

**A elisão não domina, que era o medo.** Attr embrulhado em chamada de função vira `(...)` no
plano e fica invisível. Medido: **9–20% das formas distintas, 10–14% do tráfego**. Subquery:
3–5%. A promessa do 3a não morre por aí.

**O que dá para responder, em números:** o slot de filtro existe em 61–80% do tráfego, e o
matcher resolve um attr declarado em papel de filtro em **45–62%**. Ordenação aparece em só
10–15% — as tasks da ablação eram mais de filtro que de ranking, então esse número diz mais
sobre o corpus do que sobre o instrumento.

## Três coisas que este bench NÃO mediu

1. **Índice → campo: 0%, não exercitado.** Nenhuma das duas fixtures tem `DEFINE INDEX`, então
   nenhum `IndexScan` apareceu. Numa base real com índices, parte do predicado deixa de vir
   como texto e passa a vir como `access` sem nome de campo — e aí o passo de resolução por
   cache (`INFO FOR TABLE`) entra em jogo. **Esse passo continua não medido.**
2. **Vetor e full-text:** idem, as fixtures não têm.
3. **Escala:** o corpus é de 12 a 48 linhas por tabela. Nada aqui fala sobre custo do `EXPLAIN`
   em tabela grande — isso foi medido à parte (102 µs contra 12,1 ms de query em 40k linhas).

## Um artefato do próprio bench, declarado

26 statements do round2 não parseiam em 3.1.x — mas **funcionaram** quando os agentes as
rodaram: a ablação correu contra **2.x**, onde o operador `~` existe. Ele sumiu no 3.x. Não é
lacuna de cobertura do 3a; é a replay estar numa major diferente da original. E reforça, por
acidente, o achado da condição de versão: a mesma query muda de válida para inválida entre
majors, e é por isso que `server_version` tem que estar no evento.

## Dois achados que não eram o objetivo

- **`seq` aparece 33× como "nome referenciado e não declarado" no round2.** `seq` é o campo-
  decoy que a fixture criou de propósito (a sequência de ingestão contígua, contra o `cut` que
  é a ordem real de leitura). Ou seja: o analytics do 0.2 **detectaria sozinho** que os agentes
  estão filtrando e ordenando por um campo que a ontologia não declara. É o N3 funcionando, de
  graça, sobre dado que já existia.
- **7% das chamadas do round2 carregavam mais de um statement** (até 6 numa chamada; 2% no
  round1). O contrato de "uma statement por chamada" do gateway recusaria essas. É um custo de
  adoção real que ninguém tinha quantificado.

## Um bug do matcher, corrigido e registrado

A primeira versão redigia literais substituindo por `'<lit>'` — e o tokenizador pegava `lit` de
volta, reportando **194 falsos positivos** de "campo não declarado", junto com `ASC`, `OR` e
`CONTAINS`. É exatamente o falso positivo que o desenho do matcher avisava ("redigir literais
primeiro; falso positivo aqui é *dado errado*"). O conserto: substituir por espaço, remover
record ids (`article:a6`) e filtrar as palavras-chave do SurrealQL. Os números acima são os de
depois do conserto.

## Reproduzir

```bash
uv run python evals/ablation/b2_plan_coverage.py --port 8041
```

Sobe um SurrealDB 3.x in-memory, semeia as duas fixtures em bases descartáveis, replica cada
statement distinta com `EXPLAIN`, roda o matcher e derruba o servidor.
