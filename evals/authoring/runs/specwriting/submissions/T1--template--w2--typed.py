"""Typed ontology declaration for the ticket unit type."""

from datetime import datetime
from typing import Annotated, Literal

from tank import Key, Ontology, Text, Unit


class Ticket(Unit, table="ticket", nature="original"):
    subject: Annotated[str, Key()]
    priority: Literal["p1", "p2", "p3"]
    opened_at: Annotated[datetime, Key()]
    body: Annotated[str, Text()]


ontology = Ontology.of(Ticket)
