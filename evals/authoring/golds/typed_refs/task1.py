"""Typed reference translation of task 1 — used only to verify the gold is
expressible in both forms; never shown to agents."""

from datetime import datetime
from typing import Annotated, Literal

from tank import Ontology
from tank.typed import Key, Text, Unit


class Ticket(Unit, table="ticket", nature="original"):
    subject: Annotated[str, Key()]
    body: Annotated[str, Text()]
    priority: Literal["p1", "p2", "p3"]
    opened_at: Annotated[datetime, Key()]


ontology = Ontology.of(Ticket)
