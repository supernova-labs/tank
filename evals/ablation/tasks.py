"""Task suite for the ontology ablation eval.

Each task exercises ONE ontology component (its ``category``); the ablation
matrix reads out whether removing that component hurts the tasks of its own
category. ``gold`` is programmatically checkable — record ids, never an LLM
judgement.

answer kinds:
  * ``id_set``  — answer_ids must equal gold as a set
  * ``id_list`` — answer_ids must equal gold as an ordered list
  * ``count``   — answer_count must equal gold
"""

TASKS = [
    {
        "id": "V1",
        "category": "values",
        "kind": "id_set",
        "gold": ["article:a3", "article:a7"],
        "prompt": (
            "Which articles were pulled from publication by the editors (killed stories)? "
            "Return their record ids."
        ),
    },
    {
        "id": "V2",
        "category": "values",
        "kind": "id_set",
        "gold": ["brief:b2", "brief:b5"],
        "prompt": (
            "Return the record ids of all verification / fact-checking notes in the knowledge base."
        ),
    },
    {
        "id": "L1",
        "category": "locator",
        "kind": "id_list",
        "gold": ["passage:p7", "passage:p2", "passage:p9", "passage:p4"],
        "prompt": (
            "Return the record ids of the passages of the article titled "
            "'Quantum leap at Helios Labs', in the order they appear in the article "
            "(first to last)."
        ),
    },
    {
        "id": "L2",
        "category": "locator",
        "kind": "id_set",
        "gold": ["passage:p11"],
        "prompt": (
            "Return the record id of the opening passage (the one that appears first) "
            "of the article titled 'Climate accord signed'."
        ),
    },
    {
        "id": "N1",
        "category": "nature",
        "kind": "id_set",
        "gold": ["article:a1", "article:a2", "article:a3"],
        "prompt": (
            "Return the record ids of all ORIGINAL source material (primary reporting, "
            "not derived or machine-generated notes) whose text mentions 'quantum'."
        ),
    },
    {
        "id": "N2",
        "category": "nature",
        "kind": "id_set",
        "gold": ["brief:b4", "brief:b5"],
        "prompt": (
            "Return the record ids of all DERIVED / machine-generated content units "
            "(not original reporting) whose text mentions 'climate'."
        ),
    },
    {
        "id": "G1",
        "category": "generic",
        "kind": "count",
        "gold": 5,
        "prompt": "How many articles belong to the 'Science' desk? Return the count.",
    },
    {
        "id": "G2",
        "category": "generic",
        "kind": "id_set",
        "gold": ["topic:t3"],
        "prompt": (
            "Which topics does the article titled 'Election maps redrawn' cover? "
            "Return the topic record ids."
        ),
    },
]

BY_ID = {t["id"]: t for t in TASKS}
