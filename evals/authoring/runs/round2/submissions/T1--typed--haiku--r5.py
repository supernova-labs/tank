from datetime import datetime
from typing import Annotated, Literal

from tank import Key, Ontology, Text, Unit


class Ticket(Unit, table="ticket", nature="original"):
    subject: Annotated[str, Key()]
    body: Annotated[str, Text()]
    priority: Literal["p1", "p2", "p3"]
    opened_at: Annotated[datetime, Key()]


ontology = Ontology.of(Ticket)
