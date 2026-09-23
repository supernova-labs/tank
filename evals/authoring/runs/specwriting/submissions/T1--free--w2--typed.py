"""helpdesk ontology: `ticket` — typed declaration."""

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
    body: Annotated[str, Text()]
    priority: Literal["p1", "p2", "p3"]


ontology = Ontology.of(Ticket)
