"""Helpdesk ticket ontology declaration using Tank typed classes."""

from datetime import datetime
from typing import Annotated, Literal

from tank import (
    Key,
    Ontology,
    Text,
    Unit,
)


class Ticket(Unit, table="ticket", nature="original"):
    subject: Annotated[str, Key()]
    opened_at: Annotated[datetime, Key()]
    priority: Literal["p1", "p2", "p3"]
    body: Annotated[str, Text()]


ontology = Ontology.of(Ticket)
