-- Golden fixture: tabela certa + tabela-armadilha + 12 pareceres com pegadinhas.
DEFINE TABLE parecer_tecnico SCHEMAFULL;
DEFINE FIELD codigo      ON parecer_tecnico TYPE string;
DEFINE FIELD corpo_texto ON parecer_tecnico TYPE string;
DEFINE FIELD situacao    ON parecer_tecnico TYPE string ASSERT $value IN ['vigente', 'revogado'];
DEFINE FIELD emitido_em  ON parecer_tecnico TYPE datetime;

DEFINE TABLE laudo SCHEMAFULL;
DEFINE FIELD texto  ON laudo TYPE string;
DEFINE FIELD status ON laudo TYPE string;
DEFINE FIELD data   ON laudo TYPE datetime;

CREATE parecer_tecnico:pt001 SET codigo='PT-001', corpo_texto='Parecer sobre fundação do bloco B.',        situacao='vigente',  emitido_em=d'2026-08-30T10:00:00Z';
CREATE parecer_tecnico:pt002 SET codigo='PT-002', corpo_texto='Análise estrutural da cobertura.',           situacao='vigente',  emitido_em=d'2026-08-25T10:00:00Z';
CREATE parecer_tecnico:pt003 SET codigo='PT-003', corpo_texto='Avaliação de recalque no muro de arrimo.',   situacao='revogado', emitido_em=d'2026-09-01T10:00:00Z';
CREATE parecer_tecnico:pt004 SET codigo='PT-004', corpo_texto='Inspeção de corrosão nas armaduras.',        situacao='vigente',  emitido_em=d'2026-08-20T10:00:00Z';
CREATE parecer_tecnico:pt005 SET codigo='PT-005', corpo_texto='Parecer de impermeabilização do subsolo.',   situacao='vigente',  emitido_em=d'2026-08-20T10:00:00Z';
CREATE parecer_tecnico:pt006 SET codigo='PT-006', corpo_texto='Revisão do projeto de drenagem.',            situacao='revogado', emitido_em=d'2026-07-15T10:00:00Z';
CREATE parecer_tecnico:pt007 SET codigo='PT-007', corpo_texto='Laudo de vistoria cautelar de vizinhança.',  situacao='vigente',  emitido_em=d'2026-07-10T10:00:00Z';
CREATE parecer_tecnico:pt008 SET codigo='PT-008', corpo_texto='Parecer sobre patologias em fachada.',       situacao='vigente',  emitido_em=d'2026-06-05T10:00:00Z';
CREATE parecer_tecnico:pt009 SET codigo='PT-009', corpo_texto='Análise de vibração em laje de máquinas.',   situacao='revogado', emitido_em=d'2026-05-01T10:00:00Z';
CREATE parecer_tecnico:pt010 SET codigo='PT-010', corpo_texto='Parecer geotécnico do talude norte.',        situacao='vigente',  emitido_em=d'2026-04-12T10:00:00Z';
CREATE parecer_tecnico:pt011 SET codigo='PT-011', corpo_texto='Avaliação pós-incêndio do galpão 3.',        situacao='revogado', emitido_em=d'2026-03-20T10:00:00Z';
CREATE parecer_tecnico:pt012 SET codigo='PT-012', corpo_texto='Parecer de estanqueidade do reservatório.',  situacao='revogado', emitido_em=d'2026-02-01T10:00:00Z';

CREATE laudo:l1 SET texto='Laudo de avaliação predial.',   status='ativo',     data=d'2026-08-28T10:00:00Z';
CREATE laudo:l2 SET texto='Laudo de instalação elétrica.', status='ativo',     data=d'2026-08-10T10:00:00Z';
CREATE laudo:l3 SET texto='Laudo de SPDA.',                status='arquivado', data=d'2026-06-01T10:00:00Z';
