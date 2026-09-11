# Tank

Um framework para tornar o seu acervo acessível a agentes — e provar que ele está sendo bem usado.

Tank não entrega a pipeline pronta: ela é sua. Ele oferece contratos opinionados (ontologia declarada em código, meios de acesso como funções decoradas, registro de uso e citação) que o seu projeto implementa e, por implementar, ganha capacidades: busca que respeita a sua ontologia, evidências citáveis e versionadas, verificação opcional e — o mais importante — analytics sobre como os agentes acessam o seu dado e o que foi útil. Pacote Python async, SurrealDB-first, no mesmo padrão de content-core, esperanto e ai-prompter.

Open source desde o dia zero.

## Documentos

- [`docs/rag-vision.md`](docs/rag-vision.md) — o documento de visão (história + parte técnica). É a fonte da tese.
- [`docs/rag-vision.v1-retrieval-lib.md`](docs/rag-vision.v1-retrieval-lib.md) — a versão anterior (biblioteca de retrieval), mantida como registro.
- [`docs/rag-lib-requirements.md`](docs/rag-lib-requirements.md), [`docs/rag-references.md`](docs/rag-references.md), [`docs/rag-references-libs.md`](docs/rag-references-libs.md), [`docs/rag-references-research.md`](docs/rag-references-research.md) — requisitos e referências levantados em 02/09.

## O que vem primeiro

1. Contratos + ontologia + `doctor` — declarar, validar, inspecionar.
2. Registro de uso e citação + analytics básico.
3. Meios de acesso (`@access_tool`) + registry + adapters (LangChain, MCP).

Os dois desafios reais: **indexação e ontologia** (o que a biblioteca valida × o que o projeto declara) e o **protocolo de busca**. Teste de pronto: "usa a skill do Tank sobre esta ontologia e cria uma função que encontre notícias a partir de uma entidade" — o agente tem que conseguir.

## Tank 0.1 — o validator (`tank check`)

O 0.1 entrega a primeira peça: **ontologia como código Pydantic + checagem determinística contra o SurrealDB** — sem LLM, rodável no CI. Referência dos códigos de check: [`docs/checks.md`](docs/checks.md).

**1. Declare a ontologia** (`ontology.py` no seu projeto):

```python
from tank import Attr, Ontology, StableId, UnitType

ontology = Ontology(
    types=[
        UnitType(
            "laudo",
            table="parecer_tecnico",  # a SUA tabela; o Tank nunca escreve nela
            id=StableId.of("codigo"),
            text="corpo_texto",
            attrs=[
                Attr("situacao", "string", values=["vigente", "revogado"]),
                Attr("emitido_em", "datetime"),
            ],
        ),
    ],
)
```

Uma ontologia internamente inconsistente (relação para tipo não declarado, escopo sem relação, vetor sem dimensão…) **explode no import** com todos os códigos `ONT-*` de uma vez — o build quebra antes de existir conexão com banco.

**2. Rode o check:**

```bash
uv run tank check --ontology ontology.py --url http://127.0.0.1:8000 --ns meu_ns --db meu_db
```

O relatório valida o banco contra a declaração — tabela existe? campos declarados têm `DEFINE FIELD` (ou, sem ele, estão presentes na amostra)? vocabulário de `values` bate com os dados? aresta tem a direção declarada? índice vetorial existe com a dimensão e métrica certas? — com quatro estados (`PASS`/`FAIL`/`WARN`/`VACUOUS` — tabela vazia nunca passa em silêncio), cabeçalho nomeando o ambiente validado e uma seção fixa do que **não** é verificado. Exit code ≠ 0 quebra o CI; `--strict` promove avisos a erro; `--json` para máquinas.
