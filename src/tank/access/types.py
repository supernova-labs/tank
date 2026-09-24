"""The boundary types: what an access tool hands back.

`type` is the NAME of a declared unit type, a `str` and never a class. That is
what makes the trail work for a purely declarative consumer, with no typed
layer required — and it is deliberate: Tank never wrote the row, so it does not
know its id. The caller builds the `Ref`; Tank verifies and records it.

The three stages are a hierarchy on purpose. A search returns `Candidate`s,
which are previews and are never citable. `Evidence` is what exists after
opening one, and its `excerpt` is optional because "a fact with no text" is a
real unit type, not an edge case.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Candidate", "Evidence", "Ref", "refs_from"]


class Ref(BaseModel):
    """A reference to a unit a tool returned. Not citable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str = Field(min_length=1)
    id: str = Field(min_length=1)
    scope_value: str | None = None

    @classmethod
    def of(
        cls,
        unit_type: str | Any,
        row: Mapping[str, object],
        *,
        id_field: str = "id",
        **extra: object,
    ) -> Ref:
        """Sugar for the common case: a row from the database becomes a ref.

        ``unit_type`` is the declared type name. A typed class is accepted and
        read for its ``__tank_name__``, so the same call works in both forms,
        but nothing here requires the typed layer to exist.
        """
        name = getattr(unit_type, "__tank_name__", unit_type)
        if not isinstance(name, str):
            raise TypeError(f"unit_type must be a declared type name (str), got {unit_type!r}")
        if id_field not in row:
            raise KeyError(
                f"{name}: row has no {id_field!r} to use as the reference id "
                f"(available: {sorted(row)}) — pass id_field= to name another"
            )
        return cls(type=name, id=str(row[id_field]), **extra)


class Candidate(Ref):
    """What a search returns: a preview, never citable (a candidate is a guess)."""

    score: float | None = None
    rank: int | None = None
    title: str | None = None
    preview: str | None = None
    citeable: ClassVar[bool] = False


class Evidence(Ref):
    """What exists after opening a candidate.

    ``excerpt`` is optional on purpose: the hardest acceptance case in the
    corpus is a unit type that carries a fact and no text at all.
    """

    excerpt: str | None = None
    locator: dict[str, str] = Field(default_factory=dict)
    provenance: str | None = None
    content_hash: str | None = None
    version: str | None = None
    citeable: ClassVar[bool] = True


def refs_from(
    rows: Sequence[Mapping[str, object]],
    *,
    type: str,
    id_field: str = "id",
    scope_value: str | None = None,
    stage: type[Ref] = Ref,
) -> list[Ref]:
    """A list of rows becomes a list of refs, with no ceremony.

    This exists so that the common case — a tool that ran one query and got
    dicts back — costs one line rather than a comprehension the caller has to
    get right.
    """
    return [
        stage.of(
            type, row, id_field=id_field, **({"scope_value": scope_value} if scope_value else {})
        )
        for row in rows
    ]
