# Referências — síntese para o kickoff

> Consolidação de dois relatórios de pesquisa feitos em 2026-09-02:
> - `rag-references-libs.md` — 20+ bibliotecas e produtos, com código-fonte verificado, tabela comparativa e recomendações de reuso.
> - `rag-references-research.md` — literatura e prática: avaliação de citação, APIs nativas, identidade de chunk, fusão híbrida, providers de embedding, enriquecimento de chunk, proveniência, loops de eval.
>
> Aqui só o que muda decisões. Detalhes e links nos dois arquivos.

---

## 1. O que ninguém faz (nossos diferenciais, verificados)

1. **Verificação polimórfica por tipo de unidade.** Não existe. Cada ferramenta assume uma granularidade e um método. Peças isoladas existem — Instructor (substring exata, mas descarta em falha), kotaemon (difflib a 35%), Vertex Check Grounding / HHEM / MiniCheck (entailment) — mas `QuoteMatch` + `DerivationIntact` + `Recompute` sob um protocolo, ninguém. **Recompute com id determinístico para fatos computados: nada.**
2. **Candidato ≠ evidência com receipt (hash + versão).** Hashes são usados para dedup e refresh (Haystack, LlamaIndex, Onyx), nunca como recibo de citação. A Anthropic garante ponteiro válido *dentro de uma chamada*; não há persistência. paper-qa e o contrato MCP do Deep Research (`search → ids`, `fetch(id)`) fazem dois passos **por orçamento**, não por citabilidade.
3. **Reter a versão citada após reprocessamento.** Nenhum framework RAG faz. Todos sobrescrevem. O padrão vem de data lakes (LiveVectorLake, Delta) e do W3C PROV (`wasRevisionOf`).
4. **Marcar falha sem descartar.** O mais próximo é o `AnswerBuilder` do Haystack (avisa e mantém). kotaemon e Instructor descartam em silêncio; R2R mantém com payload nulo; Onyx descarta com warning.
5. **Unidade como protocolo.** Todos expõem classe concreta (`Document`, `TextNode`, linha de chunk). Anthropic custom-content blocks e Vectara `document_parts` são unit-agnostic, mas não são protocolo Python.
6. **Proveniência que atravessa o retrieval.** GraphRAG, LightRAG, R2R e RAGFlow *armazenam* `text_unit_ids`/`source_id`, mas R2R, RAGFlow e kotaemon **perdem isso na resposta**. `supported_by` como aresta verificada não existe em lugar nenhum.
7. **Fusão medida.** Todo mundo hardcoda (5:1, 0,5/0,5, 0,7/0,3). Só o txtai escolhe por calibração. Nenhuma lib acopla eval ao ajuste.
8. **Projeção sobre banco existente com ontologia + renderers.** O único precedente sério é o **pgai Vectorizer** (Timescale): `create_vectorizer(source_table, loading, chunking, formatting, destination)` + fila/worker. Postgres-only, chunk-first. **Sobre SurrealDB: zero bibliotecas library-grade** (`langchain-surrealdb` é vector-only, 32★; o resto é hackathon).

## 2. O que já existe e não deve ser reinventado

| Peça | Reusar de | Nota |
|---|---|---|
| Fusão híbrida | **SurrealDB ≥3.0 nativo**: `search::rrf($lists, $limit, $k)` e `search::linear($lists, $weights, $limit, 'minmax'\|'zscore')` | D5 vira configuração. Padrão de 4 listas (page+section × FTS/vector) do docs-search da própria SurrealDB |
| Métricas IR e comparação de fusões | **ranx** (recall@k, MRR, nDCG + 25 fusões, testes estatísticos) | para o eval decidir RRF vs. linear |
| Verificador semântico local | **HHEM-2.1-Open** (Vectara, ~0,1B, Apache-2.0, ~1,5 s CPU) default; **MiniCheck** Flan-T5-L mais preciso; Bespoke-MiniCheck-7B (Ollama) pesado; **LettuceDetect** localiza spans não suportados | HHEM é inglês-only; teto ~80% F1 (AttributionBench) → é *sinal*, não prova |
| Semântica de "suporte" | **Vertex Check Grounding**: whole-entailment (claim parcial = não suportado), `citationThreshold` 0,6, `antiCitationIndices`; **AttrScore** 3 classes (attributable / extrapolatory / contradictory) | vocabulário de status na UI |
| Métricas de citação | **ALCE**: citation recall (entailment conjunto) e precision (remove-one); definição **AIS** ("According to P, s") | comparável com a literatura |
| QuoteMatch | validator do **Instructor** (`re.finditer(re.escape(quote))`) + tier fuzzy com RapidFuzz `partial_ratio` ≥ 85–90; âncoras START/END do kotaemon como formato tolerante a paráfrase | nunca 50 (FuzzyCitation) nem 35% (kotaemon) |
| Ids estáveis | regra do **LightRAG**: `md5(f"{len(key)}:{key}:{content}")` doc-scoped e length-prefixed; separar `id` de `content_hash` (Haystack faz id==hash e não consegue expressar "mesma unidade, nova versão"); duas gates de reindex do **Onyx** (timestamp → content_hash gravado só após escrita) | |
| Wire format de citação em stream | evento SSE `citation{id, is_new, span, payload}` do **R2R** + parser com hold-back e code-block-awareness do **Onyx** | |
| Contrato de dois passos para agentes | `search → {ids, previews}` / `fetch(id) → receipt`, **compatível com o MCP do OpenAI Deep Research** | vira conector de graça |
| Golden sets | Ragas `TestsetGenerator` (pinar 0.4.3 — repo parado desde fev/2026, 224 PRs abertos) ou DeepEval `Synthesizer` (ativo); shape `Golden{input, expected_output, context, retrieval_context}` do DeepEval | |
| Rubrica composta | `DAGMetric` do DeepEval como molde para QuoteMatch → DerivationIntact → Recompute | |
| Juiz calibrado | ARES (prediction-powered inference com ~150 anotações/domínio); Zheng et al. (swap de posição, rubrica explícita) | |
| Proveniência | **W3C PROV-O** como vocabulário: `wasQuotedFrom`, `wasDerivedFrom`, `wasGeneratedBy`, `wasRevisionOf` | emprestar o vocabulário, sem RDF |

## 3. Impacto nas decisões do kickoff

| Decisão | O que a pesquisa diz |
|---|---|
| **D3 banco compartilhado** e **pull + projeção** | O pgai Vectorizer é o modelo: declaração (source, loading, formatting, destination) + worker + cascade. Confirma que "projeção descartável sobre o banco da app" é caminho conhecido e funciona. Copiar também a rotação de chave projetada do Azure AI Search quando o pai muda. |
| **D4 formato da ontologia** | pgai é declarativo com `formatting template`; renderers em código só onde o texto é computado. Reforça "declarativo com hooks". |
| **D5 fusão** | RRF k=60 default; `search::linear` min-max só depois do eval. Bruch et al. 2023 e Weaviate mostram +4–6% para combinação convexa *calibrada*; sem calibração, RRF é mais estável. WANDS: fusão importa menos do que o que se funde (chunking/contexto > rerank > fusão). |
| **D6 esquema de id** | `hash(source_version, chunker_id+versão, ordinal)` — não hash de conteúdo puro (colide entre fontes com texto igual, GraphRAG e Haystack), não uuid (obriga RecordManager/docstore). Guardar `content_hash` separado para CDC. |
| **D7 retenção de versões** | `wasRevisionOf` + refcount de citações; cold tier = a própria tabela sem vetor, para não inflar o HNSW in-memory. Diferencial confirmado. |
| **R-E5 cited vs verified** | Adotar AIS/ALCE como contrato; HHEM como verificador default opcional; expor `citation_threshold`. |
| **R-V4 quirks de provider** | `embedding_config_hash` obrigatório por índice (provider, modelo, task_type/input_type/instrução, dims, normalização). Gemini-embedding-2 **trocou** `task_type` por instrução no prompt; embedding-001 exige normalização manual fora de 3072 dims. Sem o hash, re-embedding parcial corrompe o espaço em silêncio. |
| **R-F10 contextual retrieval** | −49% de falhas (Anthropic) mas replicação independente acha +2 pp sobre híbrido RRF e o reranker domina. Entra como transform opcional e **versionado** (é saída de LLM, não determinística); late chunking é a alternativa determinística. |
| **R-C3 candidato ≠ evidência** | Nenhum provider valida "só cita o que recebeu"; OpenAI file_search e Perplexity só chegam a nível de arquivo/URL. Delivery verification é invariante nossa. Quando o gerador for Anthropic, passar unidades abertas como custom-content blocks e tratar `cited_text` como extrato confiável — verificando ainda o suporte. |

## 4. Riscos e gotchas do SurrealDB (v3)

- HNSW é **in-memory** com cache compartilhado limitado (256 MiB default); DiskANN existe para disco; **MTREE sumiu da doc atual** — conferir a versão em uso.
- Full-text indexa **um campo por índice**; `search::score` devolve 0 para termos em ≥50% dos docs (clamp de IDF) — corpora pequenos sofrem.
- FTS e KNN rodam como consultas separadas e são fundidas depois; scope filter entra no `WHERE` do KNN (avaliado na travessia) e no `@n@`.
- `VERSION` time-travel é alpha e engine-gated → **receipts precisam de hash/versão próprios**, não podem depender disso.
- **Spectron / Agent Memory**: a SurrealDB está construindo produto fechado com RRF k=60 + graph rerank e "first-class provenance". Chunk-premised e proprietário, mas ler antes de escolher nome e narrativa.

## 5. Estado do ecossistema (para posicionamento)

- Vivos e ativos: Onyx (31,9k★), RAGFlow (89,9k★), LightRAG, LlamaIndex, Haystack, TruLens, DeepEval.
- Mortos ou parados: R2R (dormente desde nov/2025), Cognita (arquivado mar/2026), Superlinked (arquivado mai/2026), RefChecker (arquivado abr/2026), Ragas (parado desde fev/2026), GraphRAG (maintenance mode).
- Leitura: a fatia "plataforma RAG completa" consolidou em dois ou três players; a fatia "biblioteca de evidência verificável, agnóstica de framework, sobre o seu banco" está **vazia**.

## 6. O que mais me chamou a atenção

- **TruLens acabou de adicionar `citation_attribution` e `citation_accuracy`** (jul/ago 2026): separa "suportado em algum lugar" (groundedness) de "suportado pela citação" (attribution). É exatamente candidato ≠ evidência visto pelo lado da avaliação — dá para alinhar métricas.
- **LlamaIndex guarda o hash do nó de origem na aresta** (`RelatedNodeInfo.hash`) — um `DerivationIntact` barato que ninguém usa.
- **Onyx explica no README do módulo por que a fusão é fixa em 0,5/0,5** — o único lugar onde alguém discute o trade-off em vez de esconder.
- **Ragas tem `QuotedSpansAlignment`** — QuoteMatch verbatim não-LLM, pronto.
