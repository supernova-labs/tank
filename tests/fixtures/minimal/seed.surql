-- Minimal golden fixture: the right table + a decoy table + 12 rows with traps.
-- The ontology type is named "report" but lives in "technical_assessment" — on
-- purpose: an agent (or a check) must READ the declaration, not guess names.
-- The decoy table "report" holds plausible-but-wrong data.
DEFINE TABLE technical_assessment SCHEMAFULL;
DEFINE FIELD code      ON technical_assessment TYPE string;
DEFINE FIELD body_text ON technical_assessment TYPE string;
DEFINE FIELD status    ON technical_assessment TYPE string ASSERT $value IN ['current', 'revoked'];
DEFINE FIELD issued_at ON technical_assessment TYPE datetime;

DEFINE TABLE report SCHEMAFULL;
DEFINE FIELD text  ON report TYPE string;
DEFINE FIELD state ON report TYPE string;
DEFINE FIELD date  ON report TYPE datetime;

CREATE technical_assessment:ta001 SET code='TA-001', body_text='Assessment of the block B foundation.',   status='current', issued_at=d'2026-08-30T10:00:00Z';
CREATE technical_assessment:ta002 SET code='TA-002', body_text='Structural analysis of the roof.',          status='current', issued_at=d'2026-08-25T10:00:00Z';
CREATE technical_assessment:ta003 SET code='TA-003', body_text='Settlement evaluation of retaining wall.',  status='revoked', issued_at=d'2026-09-01T10:00:00Z';
CREATE technical_assessment:ta004 SET code='TA-004', body_text='Corrosion inspection of reinforcement.',    status='current', issued_at=d'2026-08-20T10:00:00Z';
CREATE technical_assessment:ta005 SET code='TA-005', body_text='Basement waterproofing assessment.',        status='current', issued_at=d'2026-08-20T10:00:00Z';
CREATE technical_assessment:ta006 SET code='TA-006', body_text='Drainage project review.',                  status='revoked', issued_at=d'2026-07-15T10:00:00Z';
CREATE technical_assessment:ta007 SET code='TA-007', body_text='Neighborhood pre-construction survey.',     status='current', issued_at=d'2026-07-10T10:00:00Z';
CREATE technical_assessment:ta008 SET code='TA-008', body_text='Facade pathology assessment.',              status='current', issued_at=d'2026-06-05T10:00:00Z';
CREATE technical_assessment:ta009 SET code='TA-009', body_text='Vibration analysis of machine slab.',       status='revoked', issued_at=d'2026-05-01T10:00:00Z';
CREATE technical_assessment:ta010 SET code='TA-010', body_text='Geotechnical assessment of north slope.',   status='current', issued_at=d'2026-04-12T10:00:00Z';
CREATE technical_assessment:ta011 SET code='TA-011', body_text='Post-fire evaluation of warehouse 3.',      status='revoked', issued_at=d'2026-03-20T10:00:00Z';
CREATE technical_assessment:ta012 SET code='TA-012', body_text='Reservoir watertightness assessment.',      status='revoked', issued_at=d'2026-02-01T10:00:00Z';

CREATE report:r1 SET text='Building condition report.',      state='active',   date=d'2026-08-28T10:00:00Z';
CREATE report:r2 SET text='Electrical installation report.', state='active',   date=d'2026-08-10T10:00:00Z';
CREATE report:r3 SET text='Lightning protection report.',    state='archived', date=d'2026-06-01T10:00:00Z';
