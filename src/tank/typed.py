"""Typed declaration: the ontology as classes. This is the public way to declare.

The consumer writes one pydantic class per unit type (``Unit``) and per edge
table (``Edge``), annotates fields, and ``Ontology.of(...)`` derives the
declarative ``Ontology`` — the internal, serializable representation that
``tank check`` validates and the skill reads. The declarative objects in
``ontology.py`` remain available for programmatic construction, but they are
not the way a project is expected to write its ontology.

Rules:

- ``Unit``/``Edge`` are plain pydantic ``BaseModel``s: usable as data models in
  the rest of the application (``News(**row)``), as typed returns from access
  tools, etc. Tank adds **no CRUD** — that stays with the app.
- Class keyword arguments carry only identity facts (``table``, ``name``,
  ``nature``, ``description`` / ``src``, ``dst``). Everything that maps to a
  field is declared on the field, with ``Annotated`` markers or the ``Link[...]``
  / ``Embedding[...]`` type constructors.
- No strings inside type subscripts other than forward references to classes
  declared later in the same module: ``Link[Feed]``, ``Link["Feed"]``,
  ``Link[Source | Note]``, ``Link[Source, "Note"]``. Names that are *not* types (relation name,
  metric, model label) live in markers: ``Named("from_feed")``,
  ``Embed(metric="cosine", model="bge-m3")`` — linters never see them as
  undefined names.
- Every model field becomes a queryable ``Attr`` unless it is a link, an
  embedding, a ``Text()`` field, the record ``id``, or marked ``Hidden()``.
  ``Literal[str, ...]`` becomes the attr's closed vocabulary.
- Computed text (entity cards, fact sentences) is a method decorated with
  ``@rendered_text``; the declaration records ``Rendered(method=...)``.
- Declaration modules must stay pure: no database connections, no settings —
  ``tank check`` imports them in CI.
"""

from __future__ import annotations

import re
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, ClassVar, Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from tank.ontology import (
    Attr,
    AttrType,
    Freshness,
    FullText,
    Locator,
    Nature,
    Ontology,
    Relation,
    Rendered,
    Scope,
    StableId,
    UnitType,
    Vector,
    VectorMetric,
    Weight,
)

__all__ = [
    "Ages",
    "DeclarationError",
    "Edge",
    "Embed",
    "Embedding",
    "Hidden",
    "Key",
    "Link",
    "Locate",
    "Named",
    "Searchable",
    "Text",
    "Unit",
    "Version",
    "Weighted",
    "build_ontology",
    "rendered_text",
]


class DeclarationError(TypeError):
    """A typed declaration is malformed (raised at class-creation or build time)."""


# ------------------------------------------------------------------ field markers
# Frozen dataclasses: pydantic keeps unknown ``Annotated`` metadata untouched.


@dataclass(frozen=True)
class Key:
    """Part of the unit's stable identity (``StableId.fields``)."""


@dataclass(frozen=True)
class Version:
    """Changes when the unit is reprocessed (``StableId.version_fields``)."""


@dataclass(frozen=True)
class Text:
    """(Part of) the text the unit is found by (``UnitType.text``). Not an attr."""


@dataclass(frozen=True)
class Locate:
    """This field plays ``role`` in the locator (``Locator(role=field)``)."""

    role: str


@dataclass(frozen=True)
class Searchable:
    """Full-text search on this field (``FullText``). One per unit type."""

    analyzer: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class Ages:
    """This datetime field drives freshness ranking (``Freshness``)."""

    decay: str


@dataclass(frozen=True)
class Weighted:
    """On an ``Edge``: this field is the ranking weight (``Weight``)."""

    higher_is_better: bool = True
    range: tuple[float, float] | None = None


@dataclass(frozen=True)
class Hidden:
    """Keep this model field out of the ontology (not a queryable attr)."""


@dataclass(frozen=True)
class Named:
    """Override the relation name of a ``Link`` field (default: the field name)."""

    name: str


@dataclass(frozen=True)
class Embed:
    """Metric and model label of an ``Embedding`` field (defaults: cosine, no label)."""

    metric: VectorMetric = "cosine"
    model: str | None = None


@dataclass(frozen=True)
class _LinkTo:
    targets: tuple[type[Unit] | str, ...]


@dataclass(frozen=True)
class _Dim:
    dim: int


class Link:
    """``Link[Target]`` — a record field pointing at another unit type
    (``Relation(kind="field_link")``). ``Target`` is a ``Unit`` class, a forward
    reference to one, or several of them: ``Link[Source | Note]`` when both
    classes already exist, ``Link[Source, "Note"]`` when one is declared later
    (or is the class being declared — a union cannot contain a string).

    Expands to ``Annotated[Any, _LinkTo(...)]``. The value type is ``Any`` on
    purpose: the SDK returns ``RecordID`` objects, raw rows carry strings, and
    the app may want the loaded target — none of that is the ontology's
    business.
    """

    def __class_getitem__(cls, item: Any) -> Any:
        targets = _union_members(item)
        for target in targets:
            if not (
                isinstance(target, str) or (isinstance(target, type) and issubclass(target, Unit))
            ):
                raise DeclarationError(
                    f"Link[...] expects a Unit class, a forward reference or a union of them, "
                    f"got {target!r}"
                )
        return Annotated[Any, _LinkTo(tuple(targets))]


class Embedding:
    """``Embedding[dim]`` — the embedding vector column (``Vector``). Metric and
    model go in an ``Embed(...)`` marker; wrap in ``| None`` for ``option<array<float>>``::

        emb: Annotated[Embedding[1536], Embed(metric="cosine", model="text-embedding-3-small")] | None = None
    """

    def __class_getitem__(cls, item: Any) -> Any:
        if not isinstance(item, int) or isinstance(item, bool):
            raise DeclarationError("Embedding[...] takes the dimension only: Embedding[1536]")
        return Annotated[list[float], _Dim(item)]


def rendered_text(method: Callable[[Any], str]) -> Callable[[Any], str]:
    """Mark a method as the unit's computed text (``UnitType.text = Rendered(method)``)."""
    method.__tank_rendered_text__ = True  # type: ignore[attr-defined]
    return method


# ------------------------------------------------------------------ type mapping

_SCALAR_TYPES: dict[type, AttrType] = {
    str: "string",
    bool: "bool",  # before int: bool is a subclass of int
    int: "int",
    float: "float",
    Decimal: "number",
    datetime: "datetime",
    timedelta: "duration",
    dict: "object",
    list: "array",
    tuple: "array",
    set: "array",
}


def _union_members(tp: Any) -> list[Any]:
    origin = get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        return list(get_args(tp))
    if isinstance(tp, tuple):
        return list(tp)
    return [tp]


def _strip_optional(tp: Any) -> Any:
    """``X | None`` / ``Optional[X]`` -> ``X``; other unions are returned as-is."""
    members = [a for a in _union_members(tp) if a is not type(None)]
    return members[0] if len(members) == 1 else tp


def _attr_type_of(tp: Any, where: str) -> tuple[AttrType, list[str] | None]:
    """Map a Python annotation to an ``AttrType`` (+ closed vocabulary for Literal)."""
    tp = _strip_optional(tp)
    origin = get_origin(tp)
    if origin is Annotated:
        return _attr_type_of(get_args(tp)[0], where)
    if origin is Literal:
        values = get_args(tp)
        if all(isinstance(v, str) for v in values):
            return "string", list(values)
        if all(isinstance(v, bool) for v in values):
            return "bool", None
        if all(isinstance(v, int) for v in values):
            return "int", None
        raise DeclarationError(f"{where}: Literal values must be all str, all int or all bool")
    if origin is not None:
        tp = origin  # list[str] -> list, dict[str, Any] -> dict
    if isinstance(tp, type):
        if issubclass(tp, BaseModel):
            return "object", None
        for base, attr_type in _SCALAR_TYPES.items():
            if issubclass(tp, base):
                return attr_type, None
    raise DeclarationError(
        f"{where}: cannot map annotation {tp!r} to an attr type — "
        "mark it Hidden() or use a supported scalar/container type"
    )


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _markers(info: FieldInfo) -> list[Any]:
    """All ``Annotated`` metadata of a field, including metadata nested inside a
    union (``Embedding[4] | None`` keeps its marker under ``Optional[...]``,
    which pydantic does not hoist into ``FieldInfo.metadata``)."""
    found = list(info.metadata)

    def walk(tp: Any) -> None:
        origin = get_origin(tp)
        if origin is Annotated:
            found.extend(get_args(tp)[1:])
            walk(get_args(tp)[0])
        elif origin is typing.Union or origin is types.UnionType:
            for member in get_args(tp):
                walk(member)

    walk(info.annotation)
    return found


def _one(markers: list[Any], kind: type, where: str) -> Any | None:
    found = [m for m in markers if isinstance(m, kind)]
    if len(found) > 1:
        raise DeclarationError(f"{where}: more than one {kind.__name__}() marker")
    return found[0] if found else None


def _reject_unknown_kwargs(cls: type, kwargs: dict[str, Any]) -> None:
    unknown = sorted(set(kwargs) - cls._CLASS_KWARGS)  # type: ignore[attr-defined]
    if unknown:
        raise DeclarationError(f"{cls.__name__}: unknown class arguments {unknown}")


# ----------------------------------------------------------------------- Unit


class Unit(BaseModel):
    """Base class for a unit type declaration::

        class News(Unit, table="news", nature="original"):
            title: Annotated[str, Key()]
            body: Annotated[str, Text(), Searchable(analyzer="az_en")]
            published_at: Annotated[datetime, Key(), Ages("30d")]
            emb: Embedding[1536] | None = None
            feed: Link[Feed]

    ``table`` is required. ``name`` defaults to the snake_case class name.
    """

    __tank_table__: ClassVar[str]
    __tank_name__: ClassVar[str]
    __tank_nature__: ClassVar[Nature]
    __tank_description__: ClassVar[str | None]
    __tank_unit__: ClassVar[UnitType | None]
    __tank_links__: ClassVar[list[tuple[str, _LinkTo, str | None]]]
    __tank_freshness__: ClassVar[list[tuple[str, Ages]]]

    _CLASS_KWARGS: ClassVar[frozenset[str]] = frozenset({"table", "name", "nature", "description"})

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # pydantic forwards non-config class kwargs here AND to
        # __pydantic_init_subclass__; object.__init_subclass__ rejects them, so
        # validate and swallow them here, consume them there (model_fields exist).
        _reject_unknown_kwargs(cls, kwargs)
        super().__init_subclass__()

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__()
        table = kwargs.get("table")
        if not table:
            raise DeclarationError(f"{cls.__name__}: `table=` is required on a Unit subclass")
        cls.__tank_table__ = table
        cls.__tank_name__ = kwargs.get("name") or _snake(cls.__name__)
        cls.__tank_nature__ = kwargs.get("nature", "original")
        cls.__tank_description__ = kwargs.get("description")
        cls.__tank_unit__, cls.__tank_links__, cls.__tank_freshness__ = _derive_unit(cls)

    @classmethod
    def unit_type(cls) -> UnitType:
        """The derived declarative ``UnitType`` for this class."""
        assert cls.__tank_unit__ is not None
        return cls.__tank_unit__


def _derive_unit(
    cls: type[Unit],
) -> tuple[UnitType, list[tuple[str, _LinkTo, str | None]], list[tuple[str, Ages]]]:
    where = cls.__name__
    key_fields: list[str] = []
    version_fields: list[str] = []
    text_fields: list[str] = []
    locator: dict[str, str] = {}
    attrs: list[Attr] = []
    vector: Vector | None = None
    fulltext: FullText | None = None
    links: list[tuple[str, _LinkTo, str | None]] = []
    freshness: list[tuple[str, Ages]] = []

    for field_name, info in cls.model_fields.items():
        markers = _markers(info)
        here = f"{where}.{field_name}"
        link = _one(markers, _LinkTo, here)
        dim = _one(markers, _Dim, here)
        embed = _one(markers, Embed, here)
        named = _one(markers, Named, here)
        is_text = _one(markers, Text, here) is not None

        if _one(markers, Key, here):
            key_fields.append(field_name)
        if _one(markers, Version, here):
            version_fields.append(field_name)
        if is_text:
            text_fields.append(field_name)
        for locate in (m for m in markers if isinstance(m, Locate)):
            if locate.role in locator:
                raise DeclarationError(f"{where}: locator role {locate.role!r} declared twice")
            locator[locate.role] = field_name
        if searchable := _one(markers, Searchable, here):
            if fulltext is not None:
                raise DeclarationError(
                    f"{where}: only one Searchable() field per unit type "
                    f"({fulltext.field!r} and {field_name!r})"
                )
            fulltext = FullText(
                field=field_name, analyzer=searchable.analyzer, language=searchable.language
            )
        if ages := _one(markers, Ages, here):
            freshness.append((field_name, ages))
        if _one(markers, Weighted, here):
            raise DeclarationError(f"{here}: Weighted() only applies to Edge fields")
        if named is not None and link is None:
            raise DeclarationError(f"{here}: Named() only applies to Link fields")
        if embed is not None and dim is None:
            raise DeclarationError(f"{here}: Embed() only applies to Embedding[...] fields")

        if dim is not None:
            if vector is not None:
                raise DeclarationError(f"{where}: only one Embedding field per unit type")
            embed = embed or Embed()
            vector = Vector(field=field_name, dim=dim.dim, metric=embed.metric, model=embed.model)
            continue
        if link is not None:
            links.append((field_name, link, named.name if named else None))
            continue
        if _one(markers, Hidden, here) is not None or is_text or field_name == "id":
            # Text() is what the unit is *found by*, not a filterable attr; the
            # record id is not a DEFINE FIELD.
            continue
        attr_type, values = _attr_type_of(info.annotation, here)
        attrs.append(
            Attr(name=field_name, type=attr_type, values=values, description=info.description)
        )

    rendered = [
        name
        for name, member in vars(cls).items()
        if callable(member) and getattr(member, "__tank_rendered_text__", False)
    ]
    if len(rendered) > 1:
        raise DeclarationError(f"{where}: only one @rendered_text method per unit type")
    if rendered and text_fields:
        raise DeclarationError(
            f"{where}: declare either Text() fields or a @rendered_text method, not both"
        )

    text: str | list[str] | Rendered | None
    if rendered:
        text = Rendered(method=rendered[0])
    elif not text_fields:
        text = None
    elif len(text_fields) == 1:
        text = text_fields[0]
    else:
        text = text_fields

    if version_fields and not key_fields:
        raise DeclarationError(f"{where}: Version() fields need at least one Key() field")

    unit = UnitType(
        name=cls.__tank_name__,
        table=cls.__tank_table__,
        nature=cls.__tank_nature__,
        id=StableId(fields=key_fields, version_fields=version_fields) if key_fields else None,
        text=text,
        attrs=attrs,
        locator=Locator(**locator) if locator else None,
        vector=vector,
        fulltext=fulltext,
        description=cls.__tank_description__,
    )
    return unit, links, freshness


# ----------------------------------------------------------------------- Edge


class Edge(BaseModel):
    """A RELATE edge table between unit types (``Relation(kind="edge")``)::

        class Mentions(Edge, src=News, dst=Entity):
            relevance: Annotated[float, Weighted()]

        class Cites(Edge, src=Note, dst=Source | Note): ...

    ``table`` defaults to the relation name, which defaults to the snake_case
    class name. Fields other than the ``Weighted()`` one are ignored by the
    ontology (edges carry no attrs in 0.1) but stay usable as data.
    """

    __tank_name__: ClassVar[str]
    __tank_table__: ClassVar[str]
    __tank_src__: ClassVar[type[Unit] | str]
    __tank_dst__: ClassVar[tuple[type[Unit] | str, ...]]
    __tank_weight__: ClassVar[Weight | None]
    __tank_description__: ClassVar[str | None]

    _CLASS_KWARGS: ClassVar[frozenset[str]] = frozenset(
        {"src", "dst", "name", "table", "description"}
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        _reject_unknown_kwargs(cls, kwargs)
        super().__init_subclass__()

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__()
        src, dst = kwargs.get("src"), kwargs.get("dst")
        if src is None or dst is None:
            raise DeclarationError(f"{cls.__name__}: `src=` and `dst=` are required on an Edge")
        name = kwargs.get("name") or _snake(cls.__name__)
        weight: Weight | None = None
        for field_name, info in cls.model_fields.items():
            if weighted := _one(_markers(info), Weighted, f"{cls.__name__}.{field_name}"):
                if weight is not None:
                    raise DeclarationError(f"{cls.__name__}: only one Weighted() field per edge")
                weight = Weight(
                    field=field_name,
                    higher_is_better=weighted.higher_is_better,
                    range=weighted.range,
                )
        cls.__tank_name__ = name
        cls.__tank_table__ = kwargs.get("table") or name
        cls.__tank_src__ = src
        cls.__tank_dst__ = tuple(_union_members(dst))
        cls.__tank_weight__ = weight
        cls.__tank_description__ = kwargs.get("description")


# ---------------------------------------------------------------------- build


def _resolve(ref: type[Unit] | str, units: dict[str, type[Unit]], where: str) -> str:
    """A class or a forward-reference name -> the declared unit *name*."""
    if isinstance(ref, str):
        for unit_cls in units.values():
            if ref in (unit_cls.__name__, unit_cls.__tank_name__):
                return unit_cls.__tank_name__
        raise DeclarationError(f"{where}: {ref!r} is not among the declared Unit classes")
    if not (isinstance(ref, type) and issubclass(ref, Unit)):
        raise DeclarationError(f"{where}: expected a Unit subclass, got {ref!r}")
    if units.get(ref.__tank_name__) is not ref:
        raise DeclarationError(
            f"{where}: links to {ref.__name__}, which is not among the declared Unit classes — "
            f"pass it to Ontology.of(...) as well"
        )
    return ref.__tank_name__


def _targets(
    refs: tuple[type[Unit] | str, ...], units: dict[str, type[Unit]], where: str
) -> str | list[str]:
    names = [_resolve(r, units, where) for r in refs]
    return names[0] if len(names) == 1 else names


def build_ontology(
    *models: type[Unit | Edge],
    scopes: list[Scope] | None = None,
    relations: list[Relation] | None = None,
    freshness: list[Freshness] | None = None,
) -> Ontology:
    """Derive the declarative ``Ontology`` from ``Unit``/``Edge`` classes.

    Hand-written ``relations``/``freshness`` are appended (escape hatch for
    what the class form cannot express). Static ``ONT-*`` checks run in the
    ``Ontology`` constructor exactly as for a hand-written declaration.
    """
    units: dict[str, type[Unit]] = {}
    edges: list[type[Edge]] = []
    for model in models:
        if isinstance(model, type) and issubclass(model, Unit):
            units[model.__tank_name__] = model
        elif isinstance(model, type) and issubclass(model, Edge):
            edges.append(model)
        else:
            raise DeclarationError(f"Ontology.of(...): {model!r} is neither a Unit nor an Edge")

    derived_relations: list[Relation] = []
    derived_freshness: list[Freshness] = []
    for unit_cls in units.values():
        for field_name, link, name in unit_cls.__tank_links__:
            where = f"{unit_cls.__name__}.{field_name}"
            derived_relations.append(
                Relation(
                    name=name or field_name,
                    from_=unit_cls.__tank_name__,
                    to=_targets(link.targets, units, where),
                    kind="field_link",
                    field=field_name,
                )
            )
        for field_name, ages in unit_cls.__tank_freshness__:
            derived_freshness.append(
                Freshness(unit_type=unit_cls.__tank_name__, field=field_name, decay=ages.decay)
            )
    for edge_cls in edges:
        derived_relations.append(
            Relation(
                name=edge_cls.__tank_name__,
                from_=_resolve(edge_cls.__tank_src__, units, f"{edge_cls.__name__}.src"),
                to=_targets(edge_cls.__tank_dst__, units, f"{edge_cls.__name__}.dst"),
                kind="edge",
                table=edge_cls.__tank_table__,
                weight=edge_cls.__tank_weight__,
                description=edge_cls.__tank_description__,
            )
        )

    return Ontology(
        types=[u.unit_type() for u in units.values()],
        relations=derived_relations + list(relations or []),
        scopes=list(scopes or []),
        freshness=derived_freshness + list(freshness or []),
    )
