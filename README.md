# Tank

Um framework para tornar o seu acervo acessível a agentes — e provar que ele está sendo bem usado.

Tank não entrega a pipeline pronta: ela é sua. Ele oferece contratos opinionados (ontologia declarada em código, meios de acesso como funções decoradas, registro de uso e citação) que o seu projeto implementa e, por implementar, ganha capacidades: busca que respeita a sua ontologia, evidências citáveis e versionadas, verificação opcional e — o mais importante — analytics sobre como os agentes acessam o seu dado e o que foi útil. Pacote Python async, SurrealDB-first, no mesmo padrão de content-core, esperanto e ai-prompter.

Aprovado como tese na Reunião de Julgamento de 04/09/2026 (Linear SUP-636). Open source desde o dia zero.

## Documentos

- [`docs/rag-vision.md`](docs/rag-vision.md) — o documento de visão (história + parte técnica). É a fonte da tese.
- [`docs/rag-vision.v1-retrieval-lib.md`](docs/rag-vision.v1-retrieval-lib.md) — a versão anterior (biblioteca de retrieval), mantida como registro.
- [`docs/rag-lib-requirements.md`](docs/rag-lib-requirements.md), [`docs/rag-references.md`](docs/rag-references.md), [`docs/rag-references-libs.md`](docs/rag-references-libs.md), [`docs/rag-references-research.md`](docs/rag-references-research.md) — requisitos e referências levantados em 02/09.

## O que vem primeiro

1. Contratos + ontologia + `doctor` — declarar, validar, inspecionar.
2. Registro de uso e citação + analytics básico.
3. Meios de acesso (`@access_tool`) + registry + adapters (LangChain, MCP).

Os dois desafios reais: **indexação e ontologia** (o que a biblioteca valida × o que o projeto declara) e o **protocolo de busca**. Teste de pronto: "usa a skill do Tank sobre esta ontologia e cria uma função que encontre notícias a partir de uma entidade" — o agente tem que conseguir.
