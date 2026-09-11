"""Ontology-as-code: the declaration a project writes and `tank check` validates.

The ontology maps the project's own tables into Tank's vocabulary. It is validated
in two stages:

1. **Statically, at construction time** (this module): internal consistency —
   unique names, cross-references that resolve, complete vector/full-text
   declarations. A broken ontology raises :class:`OntologyError` on import, so a
   broken build fails before any database is touched (ONT-* checks).
2. **Against a live SurrealDB** (`tank check`, see ``checks.py``): the declared
   tables, fields, relations and indexes actually exist and match (TBL/FLD/REL/
   VEC/FTS checks).

Design notes:
- Field names live on the *project's* tables; Tank never writes to them.
- ``Relation`` must declare its *form* (``edge`` vs ``field_link``) and direction —
  the two forms have incompatible traversal syntax in SurrealQL.
- Attrs declare the queryable fields of a type: name, type and (optionally) the
  value vocabulary — what an agent needs to write a WHERE/ORDER BY without
  guessing.
- ``nature`` is the epistemic nature of a unit type (rag-vision.md): original /
  derived / authored / computed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "Attr",
    "Freshness",
    "FullText",
    "Locator",
    "Ontology",
    "OntologyError",
    "Relation",
    "Scope",
    "StableId",
    "UnitType",
    "Vector",
    "Violation",
    "Weight",
]


class Violation(BaseModel):
    """One static-validation failure, with a stable code (ONT-xxx)."""

    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.message}"


class OntologyError(Exception):
    """Raised at construction time when the ontology is internally inconsistent.

    Carries *all* violations found, not just the first one. Deliberately not a
    ``ValueError``: pydantic wraps ``ValueError`` from validators into its own
    ``ValidationError``, which would bury the stable ONT-* codes.
    """

    def __init__(self, violations: list[Violation]):
        self.violations = violations
        lines = "\n".join(f"  {v}" for v in violations)
        super().__init__(f"ontology is invalid ({len(violations)} violation(s)):\n{lines}")


class _PosModel(BaseModel):
    """Pydantic model that also accepts positional args, in field-declaration order.

    Keeps the ergonomic style of the vision doc: ``UnitType("laudo", table=...)``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if args:
            names = list(type(self).model_fields)
            if len(args) > len(names):
                raise TypeError(
                    f"{type(self).__name__} takes at most {len(names)} positional arguments"
                )
            for name, value in zip(names, args):
                if name in kwargs:
                    raise TypeError(
                        f"{type(self).__name__} got multiple values for argument {name!r}"
                    )
                kwargs[name] = value
        super().__init__(**kwargs)


AttrType = Literal[
    "string", "int", "float", "number", "bool", "datetime", "duration", "record", "array", "object"
]


class Attr(_PosModel):
    """A queryable field of a unit type: the agent may filter/order/project by it.

    ``values`` optionally declares the closed vocabulary of the field
    (e.g. ``["vigente", "revogado"]``); ``tank check`` verifies it by sampling.
    """

    name: str = Field(min_length=1)
    type: AttrType
    values: list[str] | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _non_empty_values(self) -> Attr:
        if self.values is not None and len(self.values) == 0:
            raise ValueError(f"attr {self.name!r}: `values`, when given, must be non-empty")
        return self


class StableId(_PosModel):
    """How the stable identity of a unit is derived (field tuple, hashed by the consumer)."""

    fields: list[str] = Field(min_length=1)

    @classmethod
    def of(cls, *fields: str) -> StableId:
        return cls(fields=list(fields))


class Locator(BaseModel):
    """Where a unit lives inside its source, in the project's own terms.

    Free-form mapping ``role -> field name`` (e.g. ``source=\"codigo\"``,
    ``order=\"chunk_order\"``). Every value must be a field name (str); the
    connected checks verify those fields exist.
    """

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _all_str(self) -> Locator:
        for key, value in (self.__pydantic_extra__ or {}).items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"locator entry {key!r} must be a non-empty field name (str)")
        return self

    def fields(self) -> dict[str, str]:
        return dict(self.__pydantic_extra__ or {})


VectorMetric = Literal["cosine", "euclidean", "manhattan"]


class Vector(_PosModel):
    """Declares that a unit type is vector-searchable.

    ``tank check`` requires an ANN index on ``field`` with matching DIMENSION and
    DIST — the index is *derived* from this declaration, never declared directly. ``model`` is a human-readable embedding-model label; drift defense
    beyond the label (config hash, canary) arrives with the projection phase.
    """

    field: str = Field(min_length=1)
    dim: int = Field(ge=1)
    metric: VectorMetric = "cosine"
    model: str | None = None


class FullText(_PosModel):
    """Declares that a unit type is full-text searchable on one field.

    SurrealDB allows a single field per FTS index; declare one
    ``FullText`` per searchable field.
    """

    field: str = Field(min_length=1)
    analyzer: str | None = None
    language: str | None = None


Nature = Literal["original", "derived", "authored", "computed"]


class UnitType(_PosModel):
    """A findable type of the project's domain, mapped to the table where it lives."""

    name: str = Field(min_length=1)
    table: str = Field(min_length=1)
    nature: Nature = "original"
    id: StableId | None = None
    text: str | list[str] | None = None
    attrs: list[Attr] = Field(default_factory=list)
    locator: Locator | None = None
    vector: Vector | None = None
    fulltext: FullText | None = None
    description: str | None = None

    def declared_fields(self) -> set[str]:
        """Every field name this declaration references on ``table``."""
        fields: set[str] = set()
        if isinstance(self.text, str):
            fields.add(self.text)
        elif isinstance(self.text, list):
            fields.update(self.text)
        if self.id:
            fields.update(self.id.fields)
        fields.update(a.name for a in self.attrs)
        if self.locator:
            fields.update(self.locator.fields().values())
        if self.vector:
            fields.add(self.vector.field)
        if self.fulltext:
            fields.add(self.fulltext.field)
        return fields


class Weight(_PosModel):
    """A ranking weight stored on an edge, with declared direction semantics."""

    field: str = Field(min_length=1)
    higher_is_better: bool = True
    range: tuple[float, float] | None = None


RelationKind = Literal["edge", "field_link"]


class Relation(_PosModel):
    """A named connection between two unit types.

    ``kind="edge"``: a RELATE edge table (``table`` defaults to ``name``); may
    carry a ``weight``. ``kind="field_link"``: a record field on the *from_* type
    pointing at *to* (``field`` is required; no weight — there is nowhere to
    store it).
    ``from_``/``to`` name **unit types**, not tables.
    """

    name: str = Field(min_length=1)
    from_: str = Field(min_length=1)
    to: str = Field(min_length=1)
    kind: RelationKind = "edge"
    table: str | None = None
    field: str | None = None
    weight: Weight | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _kind_shape(self) -> Relation:
        if self.kind == "edge":
            if self.table is None:
                self.table = self.name
            if self.field is not None:
                raise ValueError(
                    f"relation {self.name!r}: `field` only applies to kind='field_link'"
                )
        else:  # field_link
            if not self.field:
                raise ValueError(
                    f"relation {self.name!r}: kind='field_link' requires `field` "
                    "(the record field on the from_ type)"
                )
            if self.table is not None:
                raise ValueError(f"relation {self.name!r}: `table` only applies to kind='edge'")
            if self.weight is not None:
                raise ValueError(
                    f"relation {self.name!r}: weight is not supported on field_link "
                    "(a record field has nowhere to store it)"
                )
        return self


class Scope(_PosModel):
    """A way to cut a search down before ranking. Opaque filter; applied first."""

    name: str = Field(min_length=1)
    via: str | None = None
    description: str | None = None


class Freshness(_PosModel):
    """What ages, and how fast: ranking signal derived from a datetime field."""

    unit_type: str = Field(min_length=1)
    field: str = Field(min_length=1)
    decay: str = Field(min_length=1)


class Ontology(_PosModel):
    """The full declaration. Construction runs the static ONT-* checks and raises
    :class:`OntologyError` (with every violation) if the declaration is
    internally inconsistent — a broken ontology fails the build with no database
    involved."""

    types: list[UnitType] = Field(min_length=1)
    relations: list[Relation] = Field(default_factory=list)
    scopes: list[Scope] = Field(default_factory=list)
    freshness: list[Freshness] = Field(default_factory=list)

    @model_validator(mode="after")
    def _static_checks(self) -> Ontology:
        violations: list[Violation] = []
        type_names = [t.name for t in self.types]
        types = set(type_names)

        # ONT-001 — unique names per collection
        for label, names in (
            ("unit type", type_names),
            ("relation", [r.name for r in self.relations]),
            ("scope", [s.name for s in self.scopes]),
        ):
            seen: set[str] = set()
            for name in names:
                if name in seen:
                    violations.append(
                        Violation(
                            code="ONT-001",
                            message=f"duplicate {label} name: {name!r}",
                        )
                    )
                seen.add(name)

        # ONT-002 — relations reference declared types
        for rel in self.relations:
            for side, ref in (("from_", rel.from_), ("to", rel.to)):
                if ref not in types:
                    violations.append(
                        Violation(
                            code="ONT-002",
                            message=(
                                f"relation {rel.name!r}: {side}={ref!r} is not a declared "
                                f"unit type (declared: {sorted(types)})"
                            ),
                        )
                    )

        # ONT-003 — scope.via references a declared relation
        relation_names = {r.name for r in self.relations}
        for scope in self.scopes:
            if scope.via is not None and scope.via not in relation_names:
                violations.append(
                    Violation(
                        code="ONT-003",
                        message=(
                            f"scope {scope.name!r}: via={scope.via!r} is not a declared relation"
                        ),
                    )
                )

        # ONT-005 — attr names unique within a type
        for unit_type in self.types:
            seen_attrs: set[str] = set()
            for attr in unit_type.attrs:
                if attr.name in seen_attrs:
                    violations.append(
                        Violation(
                            code="ONT-005",
                            message=(f"type {unit_type.name!r}: duplicate attr {attr.name!r}"),
                        )
                    )
                seen_attrs.add(attr.name)

        # ONT-008 — freshness references a declared type
        for freshness in self.freshness:
            if freshness.unit_type not in types:
                violations.append(
                    Violation(
                        code="ONT-008",
                        message=(f"freshness on {freshness.unit_type!r}: not a declared unit type"),
                    )
                )

        # ONT-009 — field_link relations: the link field must not collide with
        # a declared attr of the same name on the from_ type with a non-record type
        by_name = {t.name: t for t in self.types}
        for rel in self.relations:
            if rel.kind == "field_link" and rel.from_ in by_name:
                for attr in by_name[rel.from_].attrs:
                    if attr.name == rel.field and attr.type != "record":
                        violations.append(
                            Violation(
                                code="ONT-009",
                                message=(
                                    f"relation {rel.name!r}: field {rel.field!r} is declared "
                                    f"as attr of type {attr.type!r} on {rel.from_!r} — a "
                                    "field_link field must hold records"
                                ),
                            )
                        )

        if violations:
            raise OntologyError(violations)
        return self

    # -- convenience -----------------------------------------------------------

    def type_named(self, name: str) -> UnitType:
        for unit_type in self.types:
            if unit_type.name == name:
                return unit_type
        raise KeyError(name)

    def to_json(self, **kwargs: Any) -> str:
        """Export the declaration as JSON (the contract surface the skill reads)."""
        kwargs.setdefault("indent", 2)
        return self.model_dump_json(**kwargs)
