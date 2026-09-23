-- newsroom: ablation-eval fixture. Bigger and trickier than news_mini on purpose:
--   * `status` / `kind` use non-obvious editorial codes (closed vocabulary → tests Attr.values)
--   * `passage` order lives in `take` (newsroom jargon), with a `score` field as a
--     relevance trap and record ids shuffled w.r.t. order (→ tests Locator)
--   * `brief` is AI-derived but its name sounds human-written (→ tests nature)
DEFINE TABLE topic SCHEMAFULL;
DEFINE FIELD name ON topic TYPE string;

DEFINE TABLE article SCHEMAFULL;
DEFINE FIELD title        ON article TYPE string;
DEFINE FIELD body         ON article TYPE string;
DEFINE FIELD desk         ON article TYPE string;
DEFINE FIELD status       ON article TYPE string ASSERT $value IN ['filed', 'spiked', 'held'];
DEFINE FIELD published_at ON article TYPE datetime;

DEFINE TABLE passage SCHEMAFULL;
DEFINE FIELD content ON passage TYPE string;
DEFINE FIELD parent  ON passage TYPE record<article>;
DEFINE FIELD take    ON passage TYPE int;
DEFINE FIELD score   ON passage TYPE float;

DEFINE TABLE brief SCHEMAFULL;
DEFINE FIELD text       ON brief TYPE string;
DEFINE FIELD article    ON brief TYPE record<article>;
DEFINE FIELD kind       ON brief TYPE string ASSERT $value IN ['sum', 'ang', 'chk'];
DEFINE FIELD created_at ON brief TYPE datetime;

DEFINE TABLE covers TYPE RELATION IN article OUT topic SCHEMAFULL;

CREATE topic:t1 SET name='Quantum Computing';
CREATE topic:t2 SET name='Climate';
CREATE topic:t3 SET name='Elections';

CREATE article:a1  SET title='Quantum leap at Helios Labs',            desk='Science',  status='filed',  published_at=d'2026-06-01T10:00:00Z', body='Helios Labs claims its prototype quantum processor outperformed classical rivals on a benchmark task.';
CREATE article:a2  SET title='Cooling breakthrough in quantum chips',  desk='Science',  status='filed',  published_at=d'2026-07-10T10:00:00Z', body='A new cryogenic cooling design could make quantum chips cheaper to operate at scale.';
CREATE article:a3  SET title='Quantum startup fraud allegations',      desk='Science',  status='spiked', published_at=d'2026-08-01T10:00:00Z', body='Former employees allege the quantum startup inflated benchmark results ahead of its funding round.';
CREATE article:a4  SET title='Election maps redrawn',                  desk='Politics', status='filed',  published_at=d'2026-05-20T10:00:00Z', body='Redistricting commissions in three states published new congressional maps this week.';
CREATE article:a5  SET title='Exit poll methodology',                  desk='Politics', status='held',   published_at=d'2026-09-01T10:00:00Z', body='Methodologists dispute how exit polls weight early votes.';
CREATE article:a6  SET title='Climate accord signed',                  desk='World',    status='filed',  published_at=d'2026-04-15T10:00:00Z', body='Delegates from ninety countries signed the climate accord after marathon talks.';
CREATE article:a7  SET title='Climate data leak',                      desk='World',    status='spiked', published_at=d'2026-03-10T10:00:00Z', body='Leaked documents show gaps in national climate reporting standards.';
CREATE article:a8  SET title='Fusion milestone under review',          desk='Science',  status='held',   published_at=d'2026-08-20T10:00:00Z', body='A fusion experiment reported net energy gain; the paper is under review.';
CREATE article:a9  SET title='Ballot audit results',                   desk='Politics', status='filed',  published_at=d'2026-06-30T10:00:00Z', body='County audits confirmed ballot totals within expected error margins.';
CREATE article:a10 SET title='Trade summit outcomes',                  desk='World',    status='filed',  published_at=d'2026-02-01T10:00:00Z', body='Trade ministers concluded the summit with a joint statement on tariffs.';
CREATE article:a11 SET title='Gene therapy trial',                     desk='Science',  status='filed',  published_at=d'2026-01-15T10:00:00Z', body='A gene therapy trial reported durable results in a rare disorder.';
CREATE article:a12 SET title='Border talks stall',                     desk='World',    status='held',   published_at=d'2026-07-22T10:00:00Z', body='Negotiations over the border corridor stalled for a third week.';

-- passages of a1, ids deliberately shuffled w.r.t. take; `score` orders differently
CREATE passage:p7  SET parent=article:a1, take=1, score=0.4, content='The result was disclosed at a closed briefing in Zurich.';
CREATE passage:p2  SET parent=article:a1, take=2, score=0.9, content='Helios engineers cited a new error-suppression method.';
CREATE passage:p9  SET parent=article:a1, take=3, score=0.1, content='Independent labs have requested access to the raw data.';
CREATE passage:p4  SET parent=article:a1, take=4, score=0.7, content='Funding for the program comes from a mix of public grants.';

-- passages of a6, same construction
CREATE passage:p11 SET parent=article:a6, take=1, score=0.2, content='Ministers spoke to reporters after the signing ceremony.';
CREATE passage:p5  SET parent=article:a6, take=2, score=0.8, content='The text includes binding emission targets for 2035.';
CREATE passage:p14 SET parent=article:a6, take=3, score=0.5, content='Financing commitments remain the least settled provision.';
CREATE passage:p1  SET parent=article:a6, take=4, score=0.9, content='Ratification is expected to take up to two years.';

-- briefs are machine-derived notes; the table name deliberately sounds human-written
CREATE brief:b1 SET article=article:a1, kind='sum', created_at=d'2026-06-02T10:00:00Z', text='Digest: what Helios Labs actually demonstrated with its quantum benchmark.';
CREATE brief:b2 SET article=article:a3, kind='chk', created_at=d'2026-08-02T10:00:00Z', text='Verification notes on the quantum startup fraud allegations.';
CREATE brief:b3 SET article=article:a2, kind='ang', created_at=d'2026-07-11T10:00:00Z', text='Story angle: quantum cooling and datacenter energy budgets.';
CREATE brief:b4 SET article=article:a6, kind='sum', created_at=d'2026-04-16T10:00:00Z', text='Digest of our climate accord coverage so far.';
CREATE brief:b5 SET article=article:a6, kind='chk', created_at=d'2026-04-20T10:00:00Z', text='Verification notes on the climate accord emission figures.';
CREATE brief:b6 SET article=article:a9, kind='sum', created_at=d'2026-07-01T10:00:00Z', text='Digest of the ballot audit findings.';

RELATE article:a1->covers->topic:t1;
RELATE article:a2->covers->topic:t1;
RELATE article:a3->covers->topic:t1;
RELATE article:a6->covers->topic:t2;
RELATE article:a7->covers->topic:t2;
RELATE article:a8->covers->topic:t2;
RELATE article:a4->covers->topic:t3;
RELATE article:a5->covers->topic:t3;
RELATE article:a9->covers->topic:t3;
