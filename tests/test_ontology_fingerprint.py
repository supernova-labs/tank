"""The declaration's identity: `fingerprint()` must be stable across processes
and across cosmetic reordering, and must move whenever anything an agent could
act on changes.

The stamp is a join key without backfill — a later observation records *which*
declaration it was made against, and that column can never be recomputed. So
this file asserts both directions:

- order that is presentation (which type was written first) must NOT move it —
  otherwise a reorder for readability splits an analytics series in two for
  nothing;
- order that is meaning (the identity tuple, the concatenation order of text
  fields) MUST move it — otherwise two different declarations share a stamp.

A test that only asserted the first direction would pass just as happily on an
implementation that sorted *everything*, including the order-bearing lists. The
counterfactual is what gives it teeth.

The permutation coverage is derived from ``Ontology.model_fields``, not from a
hand-written list, because a hand-written list is exactly what has already
forgotten things (the ``Locator`` roles and the ``Attr.values`` mapping keys
were both missed by the canonicalizer that lived in ``evals/authoring``). A new
list-valued field shows up here as a failure asking to be classified.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from tank import (
    Attr,
    Freshness,
    FullText,
    Locator,
    Ontology,
    Relation,
    Scope,
    StableId,
    UnitType,
    Vector,
    Weight,
)
from tank.ontology import _ORDER_IS_MEANING, _ORDER_IS_NOISE


def reference() -> Ontology:
    """Exercises every list path in the model, each with at least two entries.

    Two entries is the minimum that makes a permutation observable; with one,
    both directions of the test pass vacuously.
    """
    return Ontology(
        name="newsroom",
        version="1.4.0",
        types=[
            UnitType(
                "news",
                table="news",
                nature="original",
                id=StableId.of("slug", "published_at", version=["text_version", "chunker"]),
                text=["headline", "body"],
                locator=Locator(source="slug", order="chunk_order"),
                attrs=[
                    Attr("desk", "string", values={"c_04": "science", "c_11": "politics"}),
                    Attr("status", "string", values=["draft", "published"]),
                ],
                vector=Vector("emb", 4, "cosine"),
                fulltext=FullText("body", analyzer="az_en", language="english"),
            ),
            UnitType(
                "entity",
                table="entity",
                attrs=[Attr("kind", "string"), Attr("name", "string")],
            ),
        ],
        relations=[
            Relation("about", "news", "entity", weight=Weight("relevance", range=(0.0, 1.0))),
            # multi-target: exercises the `relations.to` list path
            Relation("cites", "news", ["news", "entity"]),
        ],
        scopes=[Scope("desk"), Scope("byline")],
        freshness=[
            Freshness("news", "published_at", "30d"),
            Freshness("entity", "seen_at", "90d"),
        ],
    )


# ------------------------------------------------------- deriving the coverage


def _concrete(annotation: object) -> list[object]:
    """The concrete types inside an annotation, unwrapping Optional/Union."""
    if get_origin(annotation) in (Union, UnionType):
        out: list[object] = []
        for arg in get_args(annotation):
            out.extend(_concrete(arg))
        return out
    return [annotation]


def _is_model(tp: object) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def model_list_paths(model: type[BaseModel], prefix: str = "") -> set[str]:
    """Every dotted path under ``model`` that holds a list or a tuple."""
    paths: set[str] = set()
    for name, field in model.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name
        for tp in _concrete(field.annotation):
            origin = get_origin(tp)
            if origin in (list, tuple):
                paths.add(path)
                for arg in get_args(tp):
                    if _is_model(arg):
                        paths |= model_list_paths(arg, path)
            elif _is_model(tp):
                paths |= model_list_paths(tp, path)
    return paths


def test_every_list_path_in_the_model_is_classified():
    """A new list-valued field must be classified before it can be hashed.

    This is the test that fails when someone adds, say, ``Relation.to: str |
    list[str]`` — which is a real pending change. Failing here is the point: the
    canonicalizer cannot guess whether the new order is meaning or noise, and
    guessing either way corrupts the stamp.
    """
    found = model_list_paths(Ontology)
    classified = _ORDER_IS_MEANING | _ORDER_IS_NOISE
    assert found - classified == set(), (
        "unclassified list path(s) — add each to _ORDER_IS_MEANING or "
        "_ORDER_IS_NOISE in tank.ontology"
    )
    assert classified - found == set(), "classified path(s) that no longer exist in the model"


def test_the_reference_ontology_exercises_every_classified_path():
    """Guards the guard: a path with fewer than two entries permutes to itself."""
    dump = reference().model_dump()
    for path in _ORDER_IS_MEANING | _ORDER_IS_NOISE:
        found = _collect(dump, path)
        assert found, f"reference() has no list at {path!r}"
        assert all(len(seq) >= 2 for seq in found), (
            f"reference() has a list at {path!r} with fewer than 2 entries — "
            "permuting it proves nothing"
        )


# ------------------------------------------------------------------ permuting


def _collect(node: object, target: str, path: str = "") -> list[list | tuple]:
    out: list[list | tuple] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.extend(_collect(value, target, f"{path}.{key}" if path else key))
    elif isinstance(node, (list, tuple)):
        if path == target:
            out.append(node)
        for item in node:
            out.extend(_collect(item, target, path))
    return out


def _reversed_at(node: object, target: str, path: str = "") -> object:
    """A copy of ``node`` with every list/tuple at ``target`` reversed."""
    if isinstance(node, dict):
        return {k: _reversed_at(v, target, f"{path}.{k}" if path else k) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        items = [_reversed_at(i, target, path) for i in node]
        return list(reversed(items)) if path == target else items
    return node


@pytest.mark.parametrize("path", sorted(_ORDER_IS_NOISE))
def test_reordering_presentation_does_not_move_the_fingerprint(path):
    base = reference()
    permuted = Ontology(**_reversed_at(base.model_dump(), path))
    assert permuted.fingerprint() == base.fingerprint(), (
        f"reordering {path!r} moved the stamp — an analytics series would split "
        "in two over a cosmetic edit"
    )


@pytest.mark.parametrize("path", sorted(_ORDER_IS_MEANING))
def test_reordering_meaning_does_move_the_fingerprint(path):
    base = reference()
    permuted = Ontology(**_reversed_at(base.model_dump(), path))
    assert permuted.fingerprint() != base.fingerprint(), (
        f"reordering {path!r} left the stamp unchanged — two declarations that "
        "mean different things would share an identity"
    )


def test_locator_roles_are_order_free():
    """``Locator`` is ``extra="allow"``, so its roles never reach model_fields —
    the coverage test above cannot see them and this is the only guard."""
    one = reference()
    other = reference()
    unit = other.types[0]
    roles = unit.locator.fields()
    unit.locator = Locator(**dict(reversed(list(roles.items()))))
    assert other.fingerprint() == one.fingerprint()


def test_attr_value_mapping_keys_are_order_free():
    """Same blind spot: mapping keys live in a dict, not in a list path."""
    one = reference()
    other = reference()
    attr = other.types[0].attrs[0]
    assert isinstance(attr.values, dict)
    attr.values = dict(reversed(list(attr.values.items())))
    assert other.fingerprint() == one.fingerprint()


# ------------------------------------------------------------------ sensitivity


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("name", lambda o: o.model_copy(update={"name": "newsroom2"})),
        ("version", lambda o: o.model_copy(update={"version": "1.4.1"})),
        ("table", lambda o: _with_type(o, table="news_v2")),
        ("nature", lambda o: _with_type(o, nature="derived")),
        ("attr type", lambda o: _with_attr(o, type="int")),
        (
            "vocabulary meaning",
            lambda o: _with_attr(o, values={"c_04": "sport", "c_11": "politics"}),
        ),
        (
            "vocabulary code",
            lambda o: _with_attr(o, values={"c_05": "science", "c_11": "politics"}),
        ),
    ],
)
def test_meaningful_changes_move_the_fingerprint(label, mutate):
    base = reference()
    assert mutate(base).fingerprint() != base.fingerprint(), f"{label} did not move the stamp"


def _with_type(ontology: Ontology, **changes) -> Ontology:
    dump = ontology.model_dump()
    dump["types"][0].update(changes)
    return Ontology(**dump)


def _with_attr(ontology: Ontology, **changes) -> Ontology:
    dump = ontology.model_dump()
    dump["types"][0]["attrs"][0].update(changes)
    return Ontology(**dump)


def test_name_and_version_are_part_of_the_hashed_payload():
    """Two projects that declare the same shape must not collide."""
    dump = reference().model_dump()
    a = Ontology(**{**dump, "name": "newsroom"})
    b = Ontology(**{**dump, "name": "archive"})
    assert a.fingerprint() != b.fingerprint()


def test_description_is_not_cosmetic():
    """Descriptions are what an agent reads; changing one changes the contract.

    Measured in the authoring ablation: the same vocabulary with and without
    meanings cost six queries versus one. A description edit is a real edit.
    """
    base = reference()
    dump = base.model_dump()
    dump["types"][0]["description"] = "wire copy, published"
    assert Ontology(**dump).fingerprint() != base.fingerprint()


# ----------------------------------------------------------------- the golden


GOLDEN = "newsroom@1.4.0+4f557e61e66b"


def test_golden_stamp_is_frozen():
    """The stamp of ``reference()``, frozen.

    If this fails, the canonical form changed. That is allowed, but it is never
    incidental: every stamp already written to an `access_event` refers to the
    old form, and the two series cannot be joined. Changing this constant is a
    decision to declare a break in the series, not a test fix.
    """
    assert reference().stamp() == GOLDEN


def test_fingerprint_is_stable_across_processes():
    """PYTHONHASHSEED randomizes set/str hashing per process; if any of it leaked
    into the canonical form, the stamp would differ between two runs of the same
    declaration — and the join key would be worthless."""
    here = Path(__file__).parent
    code = (
        f"import sys; sys.path.insert(0, {str(here)!r});"
        "from test_ontology_fingerprint import reference; print(reference().fingerprint())"
    )
    # Two subprocesses, each with its own hash seed, plus this one.
    seen = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("0", "1")
    }
    assert seen == {reference().fingerprint()}


def test_canonical_json_is_actually_canonical():
    """Sanity: the canonical form is parseable JSON with sorted object keys."""
    payload = reference().canonical_json()
    parsed = json.loads(payload)
    assert list(parsed) == sorted(parsed)
    assert parsed["name"] == "newsroom"


def test_an_unclassified_list_path_raises_instead_of_guessing(monkeypatch):
    """The failure mode is loud by design: no stamp beats a wrong stamp."""
    monkeypatch.setattr("tank.ontology._ORDER_IS_NOISE", _ORDER_IS_NOISE - {"types"})
    with pytest.raises(RuntimeError, match="not classified"):
        reference().fingerprint()
