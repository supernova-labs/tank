"""The check report: findings with stable codes, four verdict states, and an
explicit "not verified" section.

Design rules:
- ``VACUOUS`` is a first-class state — an empty table passing every sampling
  check proves nothing, and must never be printed as PASS.
- The header names the exact environment (server, version, ns, db, row counts):
  a report is only valid for the environment it names.
- Every report carries the fixed "not verified" list. A validator that stays
  silent about what it did not check manufactures false confidence.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["PASS", "FAIL", "WARN", "VACUOUS", "INFO"]

NOT_VERIFIED: list[str] = [
    "semantics of names — whether a declared type/relation means what you think it means",
    (
        "embedding model identity — only the declared label is known in 0.1 (config-hash and "
        "canary defenses arrive with the projection phase)"
    ),
    "content quality or completeness of the data itself",
    "search/ranking behavior — no access queries are executed by `tank check`",
    "semantic direction of relations — structure is checked, meaning is not",
    (
        "sampling coverage — samples read the first N rows (typically the oldest), and a "
        "field explicitly set to null counts as present"
    ),
    (
        "declared-but-inert constructs — `nature` and `StableId.version_fields` are recorded "
        "in the declaration but no 0.1 check consumes them yet"
    ),
    (
        "index location — 0.1 requires ANN/FTS indexes in the consumer's own tables; a "
        "Tank-owned index projection would move these checks' target"
    ),
]


class Finding(BaseModel):
    """One check result against one subject."""

    code: str
    status: Status
    subject: str  # e.g. "type:report", "relation:mentions", "freshness:news"
    table: str | None = None
    message: str

    def __str__(self) -> str:  # pragma: no cover - formatting
        return f"{self.status:7s} {self.code:8s} {self.subject}: {self.message}"


class Report(BaseModel):
    server_url: str
    server_version: str | None = None
    namespace: str
    database: str
    table_counts: dict[str, int] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    not_verified: list[str] = Field(default_factory=lambda: list(NOT_VERIFIED))

    def add(
        self,
        code: str,
        status: Status,
        subject: str,
        message: str,
        table: str | None = None,
    ) -> None:
        self.findings.append(
            Finding(code=code, status=status, subject=subject, table=table, message=message)
        )

    def count(self, status: Status) -> int:
        return sum(1 for f in self.findings if f.status == status)

    def exit_code(self, strict: bool = False) -> int:
        if self.count("FAIL"):
            return 1
        if strict and (self.count("WARN") or self.count("VACUOUS")):
            return 1
        return 0

    def render_text(self) -> str:
        lines: list[str] = []
        lines.append("tank check")
        lines.append(f"  server:    {self.server_url} ({self.server_version or 'version unknown'})")
        lines.append(f"  target:    ns={self.namespace} db={self.database}")
        if self.table_counts:
            counts = ", ".join(f"{t}={n}" for t, n in sorted(self.table_counts.items()))
            lines.append(f"  tables:    {counts}")
        lines.append("")
        for finding in self.findings:
            lines.append(f"  {finding}")
        lines.append("")
        summary = (
            f"  {self.count('PASS')} pass, {self.count('FAIL')} fail, "
            f"{self.count('WARN')} warn, {self.count('VACUOUS')} vacuous"
        )
        lines.append(summary)
        lines.append("")
        lines.append("  A PASS here means: the declaration is not contradicted by the schema")
        lines.append("  and the sampled data of THIS environment. Not verified:")
        for item in self.not_verified:
            lines.append(f"    - {item}")
        lines.append("")
        lines.append("  Code reference: docs/checks.md")
        return "\n".join(lines)
