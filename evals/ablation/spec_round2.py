"""Round 2 spec — hardened after round 1's ceiling effect.

Round 1 findings this spec attacks:
  * vocabulary was guessable ('spiked') and discoverable in one cheap dump →
    round 2 uses opaque codes (c_04/c_11/c_23, t1/t2/t3): the *list* is still
    discoverable, but the semantics→code mapping is undeclarable in today's
    model (Attr.values is a bare list) — the new ``full_plus`` variant carries
    the mapping in the attr description, testing the missing feature
  * order was self-evident (take=1,2,3,4 in a SELECT *) → round 2's true order
    is ``cut`` (irregular char offsets) against a ``seq`` decoy (contiguous
    ingestion order, shuffled w.r.t. reading order): the decoy now looks MORE
    like an order than the real field
  * nature was inferable from the table name → ``factbox`` (original, sounds
    machine-made) against ``brief`` (derived, sounds human-written)
  * dataset 4x bigger (48 articles) so full-table dumps hit output truncation

Golds are computed from DATA, never hand-counted.
Run ``uv run python evals/ablation/spec_round2.py`` to (re)write the fixture.
"""

import json
from pathlib import Path

from spec_round1 import minimal_of, none_of, strip_keys

from tank import (
    Attr,
    Freshness,
    Locator,
    Ontology,
    Relation,
    Scope,
    StableId,
    UnitType,
)

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "newsroom2.surql"

DESKS = ["Science", "Politics", "World", "Culture"]
KILLED = {7, 19, 33}  # status c_11
EMBARGOED = {5, 12, 28, 41}  # status c_23

SPECIAL_ARTICLES = {
    9: (
        "Helios processor milestone",
        "Helios Labs reports a quantum processor milestone verified by two partner labs.",
    ),
    21: (
        "Cryogenics reach datacenters",
        "Cryogenic advances put quantum hardware within reach of mid-size datacenters.",
    ),
    33: (
        "Venture benchmark dispute",
        "Sources allege the quantum venture misstated benchmark conditions.",
    ),
    6: (
        "Accord after marathon talks",
        "Ninety delegations signed the climate accord after marathon talks.",
    ),
    15: (
        "Disclosure gaps flagged",
        "Auditors flag gaps in climate disclosures across three industries.",
    ),
    10: (
        "Election maps redrawn",
        "Redistricting commissions published new congressional maps this week.",
    ),
}


def articles() -> list[dict]:
    rows = []
    for i in range(1, 49):
        desk = DESKS[(i - 1) % 4]
        status = "c_11" if i in KILLED else "c_23" if i in EMBARGOED else "c_04"
        title, body = SPECIAL_ARTICLES.get(
            i, (f"{desk} desk report {i}", f"Standing coverage item {i} from the {desk} desk.")
        )
        rows.append(
            {
                "id": f"a{i}",
                "title": title,
                "body": body,
                "desk": desk,
                "status": status,
                "published_at": f"2026-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}T10:00:00Z",
            }
        )
    return rows


# reading order 1..5 → (record id, char offset `cut`, ingestion order `seq`);
# ordering by seq or by record id must NOT reproduce the reading order
PASSAGES = {
    "a9": [
        ("p8", 0, 4, "The announcement followed months of quiet verification work."),
        ("p3", 214, 1, "Partner labs replicated the measurement under separate protocols."),
        ("p12", 433, 5, "Error rates stayed within the disclosed tolerance band."),
        ("p5", 689, 3, "Funding sources for the program were not disclosed."),
        ("p10", 912, 2, "A technical paper is expected before the end of the quarter."),
    ],
    "a6": [
        ("p1", 0, 2, "Ministers addressed reporters after the closing session."),
        ("p14", 198, 5, "The final text includes binding reporting requirements."),
        ("p6", 377, 1, "Several delegations recorded formal reservations."),
        ("p9", 590, 4, "Implementation committees will convene within a year."),
        ("p2", 803, 3, "Ratification timelines vary by signatory."),
    ],
}

# kind codes: t1 = digest, t2 = story angle, t3 = verification/fact-check
BRIEFS = [
    ("b1", "a9", "t1", "Digest of the Helios milestone coverage."),
    ("b2", "a9", "t2", "Angle: quantum hardware pricing pressure."),
    ("b3", "a6", "t1", "Digest of the climate accord coverage."),
    ("b4", "a15", "t2", "Angle: climate disclosure rules and mid-cap firms."),
    ("b5", "a6", "t3", "Verification pass on the climate accord figures."),
    ("b6", "a10", "t1", "Digest of the redistricting coverage."),
    ("b7", "a21", "t2", "Angle: quantum cooling supply chains."),
    ("b8", "a33", "t1", "Digest of the quantum venture allegations."),
    ("b9", "a33", "t3", "Verification pass on the quantum venture claims."),
    ("b10", "a4", "t2", "Angle: festival funding and city budgets."),
    ("b11", "a10", "t3", "Verification pass on the redistricting map data."),
    ("b12", "a12", "t1", "Digest of the exit poll methodology debate."),
]

FACTBOXES = [
    ("f1", "Turnout at a glance", "Historical turnout figures for the last five cycles."),
    ("f2", "Redistricting glossary", "Terms used in map-drawing coverage, defined."),
    ("f3", "Festival economics", "Attendance and budget figures for major festivals."),
    ("f4", "Timeline of Helios claims", "Key dates in the quantum program, compiled from filings."),
    ("f5", "Fusion research primer", "How net energy gain is measured in fusion experiments."),
    ("f6", "The accord by the numbers", "Emission targets under the climate accord, by region."),
    ("f7", "Error correction primer", "How quantum error correction is benchmarked, at a glance."),
    ("f8", "Ballot audit basics", "What county-level ballot audits do and do not verify."),
]

TOPICS = [("t1", "Quantum Computing"), ("t2", "Climate"), ("t3", "Elections"), ("t4", "Culture")]
COVERS = [
    ("a9", "t1"),
    ("a21", "t1"),
    ("a33", "t1"),
    ("a6", "t2"),
    ("a15", "t2"),
    ("a10", "t3"),
    ("a22", "t3"),
    ("a4", "t4"),
    ("a8", "t4"),
]


def write_surql() -> None:
    lines = [
        "-- newsroom2: round-2 ablation fixture (generated by spec_round2.py — edit that, not this)",
        "DEFINE TABLE topic SCHEMAFULL;",
        "DEFINE FIELD name ON topic TYPE string;",
        "",
        "DEFINE TABLE article SCHEMAFULL;",
        "DEFINE FIELD title        ON article TYPE string;",
        "DEFINE FIELD body         ON article TYPE string;",
        "DEFINE FIELD desk         ON article TYPE string;",
        "DEFINE FIELD status       ON article TYPE string ASSERT $value IN ['c_04', 'c_11', 'c_23'];",
        "DEFINE FIELD published_at ON article TYPE datetime;",
        "",
        "DEFINE TABLE passage SCHEMAFULL;",
        "DEFINE FIELD content ON passage TYPE string;",
        "DEFINE FIELD parent  ON passage TYPE record<article>;",
        "DEFINE FIELD cut     ON passage TYPE int;",
        "DEFINE FIELD seq     ON passage TYPE int;",
        "",
        "DEFINE TABLE brief SCHEMAFULL;",
        "DEFINE FIELD text       ON brief TYPE string;",
        "DEFINE FIELD article    ON brief TYPE record<article>;",
        "DEFINE FIELD kind       ON brief TYPE string ASSERT $value IN ['t1', 't2', 't3'];",
        "DEFINE FIELD created_at ON brief TYPE datetime;",
        "",
        "DEFINE TABLE factbox SCHEMAFULL;",
        "DEFINE FIELD heading ON factbox TYPE string;",
        "DEFINE FIELD body    ON factbox TYPE string;",
        "",
        "DEFINE TABLE covers TYPE RELATION IN article OUT topic SCHEMAFULL;",
        "",
    ]
    for tid, name in TOPICS:
        lines.append(f"CREATE topic:{tid} SET name='{name}';")
    for a in articles():
        lines.append(
            f"CREATE article:{a['id']} SET title='{a['title']}', desk='{a['desk']}', "
            f"status='{a['status']}', published_at=d'{a['published_at']}', body='{a['body']}';"
        )
    for parent, rows in PASSAGES.items():
        for pid, cut, seq, content in rows:
            lines.append(
                f"CREATE passage:{pid} SET parent=article:{parent}, cut={cut}, seq={seq}, "
                f"content='{content}';"
            )
    for i, (bid, aid, kind, text) in enumerate(BRIEFS, start=1):
        lines.append(
            f"CREATE brief:{bid} SET article=article:{aid}, kind='{kind}', "
            f"created_at=d'2026-{(i % 12) + 1:02d}-10T12:00:00Z', text='{text}';"
        )
    for fid, heading, body in FACTBOXES:
        lines.append(f"CREATE factbox:{fid} SET heading='{heading}', body='{body}';")
    for aid, tid in COVERS:
        lines.append(f"RELATE article:{aid}->covers->topic:{tid};")
    FIXTURE.write_text("\n".join(lines) + "\n")


# ---- golds, computed from the data ---------------------------------------------


def _golds() -> dict:
    arts = articles()
    return {
        "V1": [f"article:{a['id']}" for a in arts if a["status"] == "c_11"],
        "V2": [f"brief:{b[0]}" for b in BRIEFS if b[2] == "t3"],
        "L1": [f"passage:{p[0]}" for p in PASSAGES["a9"]],
        "L2": [f"passage:{PASSAGES['a6'][0][0]}"],
        "N1": [f"article:{a['id']}" for a in arts if "quantum" in a["body"]]
        + [f"factbox:{f[0]}" for f in FACTBOXES if "quantum" in f[2]],
        "N2": [f"brief:{b[0]}" for b in BRIEFS if "climate" in b[3]],
        "G1": sum(1 for a in arts if a["desk"] == "Science"),
        "G2": ["topic:t3"],
    }


_G = _golds()

TASKS = [
    {
        "id": "V1",
        "category": "values",
        "kind": "id_set",
        "gold": _G["V1"],
        "prompt": (
            "Which articles were killed (pulled from publication) by the editors? "
            "Return their record ids."
        ),
    },
    {
        "id": "V2",
        "category": "values",
        "kind": "id_set",
        "gold": _G["V2"],
        "prompt": (
            "Return the record ids of all verification / fact-checking notes in the knowledge base."
        ),
    },
    {
        "id": "L1",
        "category": "locator",
        "kind": "id_list",
        "gold": _G["L1"],
        "prompt": (
            "Return the record ids of the passages of the article titled "
            "'Helios processor milestone', in the order they appear in the article "
            "(first to last)."
        ),
    },
    {
        "id": "L2",
        "category": "locator",
        "kind": "id_set",
        "gold": _G["L2"],
        "prompt": (
            "Return the record id of the opening passage (the one that appears first) "
            "of the article titled 'Accord after marathon talks'."
        ),
    },
    {
        "id": "N1",
        "category": "nature",
        "kind": "id_set",
        "gold": _G["N1"],
        "prompt": (
            "Return the record ids of all ORIGINAL source material (primary reporting "
            "or human-curated reference — NOT machine-derived notes) whose text "
            "mentions 'quantum'."
        ),
    },
    {
        "id": "N2",
        "category": "nature",
        "kind": "id_set",
        "gold": _G["N2"],
        "prompt": (
            "Return the record ids of all DERIVED / machine-generated content units "
            "(not original reporting, not curated reference material) whose text "
            "mentions 'climate'."
        ),
    },
    {
        "id": "G1",
        "category": "generic",
        "kind": "count",
        "gold": _G["G1"],
        "prompt": "How many articles belong to the 'Science' desk? Return the count.",
    },
    {
        "id": "G2",
        "category": "generic",
        "kind": "id_set",
        "gold": _G["G2"],
        "prompt": (
            "Which topics does the article titled 'Election maps redrawn' cover? "
            "Return the topic record ids."
        ),
    },
]


# ---- ontology + variants -------------------------------------------------------


def build() -> Ontology:
    return Ontology(
        name="ablation_news",
        version="2.0.0",
        types=[
            UnitType(
                "article",
                table="article",
                nature="original",
                id=StableId.of("title", "published_at"),
                text="body",
                attrs=[
                    Attr("title", "string"),
                    Attr("desk", "string", description="newsroom desk that produced the piece"),
                    Attr(
                        "status",
                        "string",
                        values=["c_04", "c_11", "c_23"],
                        description="editorial status",
                    ),
                    Attr("published_at", "datetime"),
                ],
                description="a news article",
            ),
            UnitType(
                "passage",
                table="passage",
                nature="original",
                text="content",
                locator=Locator(source="parent", order="cut"),
                description="a span of an article's body",
            ),
            UnitType(
                "brief",
                table="brief",
                nature="derived",
                text="text",
                attrs=[
                    Attr("kind", "string", values=["t1", "t2", "t3"]),
                    Attr("created_at", "datetime"),
                ],
                description="short note attached to an article",
            ),
            UnitType(
                "factbox",
                table="factbox",
                nature="original",
                text="body",
                attrs=[Attr("heading", "string")],
                description="curated data box",
            ),
            UnitType("topic", table="topic", attrs=[Attr("name", "string")]),
        ],
        relations=[
            Relation("covers", "article", "topic"),
            Relation("part_of", "passage", "article", kind="field_link", field="parent"),
            Relation("notes_on", "brief", "article", kind="field_link", field="article"),
        ],
        scopes=[Scope("topic", via="covers")],
        freshness=[Freshness("article", "published_at", "30d")],
    )


VALUE_SEMANTICS = {
    "status": "editorial status: c_04 = published, c_11 = killed/pulled by the editors, c_23 = embargoed",
    "kind": "note kind: t1 = digest, t2 = story angle, t3 = verification/fact-check",
}


def _full_plus(full: dict) -> dict:
    plus = json.loads(json.dumps(full))
    for unit_type in plus["types"]:
        for attr in unit_type.get("attrs") or []:
            if attr["name"] in VALUE_SEMANTICS:
                attr["description"] = VALUE_SEMANTICS[attr["name"]]
    return plus


def variants() -> dict:
    full = json.loads(build().to_json())
    return {
        "full": full,
        "full_plus": _full_plus(full),
        "no_values": strip_keys(full, {"values"}),
        "no_locator": strip_keys(full, {"locator"}),
        "no_nature": strip_keys(full, {"nature"}),
        "minimal": minimal_of(full),
        "none": none_of(full),
    }


if __name__ == "__main__":
    write_surql()
    print(f"fixture → {FIXTURE}")
    print(json.dumps(_golds(), indent=2))
