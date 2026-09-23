"""Score round 4: how often an AI-written brief induced a wrong declaration.

One judged submission per (brief, arm); no iteration. A brief "induced an error"
when an implementation that followed it diverged from the gold the writer saw.

Usage: uv run python evals/authoring/score_specwriting.py [--round specwriting]
"""

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent

FAMILIES = (
    ("índice indevido (fulltext/vector)", lambda d: "fulltext" in d or "vector" in d),
    ("text mapping", lambda d: ".text " in d or d.endswith(".text") or ".text=" in d),
    ("vocabulário (values)", lambda d: ".values" in d),
    ("nome de tipo/relação", lambda d: ".name" in d or ".from_" in d or ".to" in d),
    ("identidade (id)", lambda d: ".id" in d),
    ("locator", lambda d: "locator" in d),
)


def family_of(diff: str) -> str:
    for name, match in FAMILIES:
        if match(diff):
            return name
    return "outros"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", default="specwriting")
    args = parser.parse_args()

    round_dir = HERE / "runs" / args.round
    manifest = json.loads((round_dir / "manifest.json").read_text())

    rows = []
    for brief in manifest:
        for arm in brief["arms"]:
            log_path = round_dir / "log" / f"{arm['run_id']}.jsonl"
            entries = (
                [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
                if log_path.exists()
                else []
            )
            first = entries[0] if entries else None
            rows.append(
                {
                    "brief_id": brief["brief_id"],
                    "task": brief["task"],
                    "style": brief["style"],
                    "writer": brief["writer"],
                    "arm": arm["arm"],
                    "judged": first is not None,
                    "constructs": bool(first and first.get("constructs")),
                    "exact": bool(first and first.get("exact")),
                    "diff_count": first.get("diff_count") if first else None,
                    "diffs": (first or {}).get("diffs") or [],
                }
            )

    results_dir = HERE / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / f"{args.round}_scored.json").write_text(json.dumps(rows, indent=2))

    cells = defaultdict(list)
    for row in rows:
        cells[(row["style"], row["arm"])].append(row)

    lines = [f"# Spec-writing eval ({args.round})", ""]
    lines.append("Uma submissão por (brief, braço), sem loop de correção.")
    lines.append("")
    lines.append("| estilo do brief | braço | implementações fiéis | diffs medianos quando erra |")
    lines.append("|---|---|---|---|")
    for style in ("free", "template"):
        for arm in ("declarative", "typed"):
            runs = cells.get((style, arm), [])
            if not runs:
                continue
            ok = sum(r["exact"] for r in runs)
            bad = [r["diff_count"] for r in runs if not r["exact"] and r["diff_count"]]
            med = f"{statistics.median(bad):g}" if bad else "—"
            lines.append(f"| {style} | {arm} | {ok}/{len(runs)} | {med} |")

    lines += ["", "## Briefs que induziram erro (por brief, somando os dois braços)", ""]
    by_brief = defaultdict(list)
    for row in rows:
        by_brief[(row["style"], row["brief_id"])].append(row)
    for style in ("free", "template"):
        induced = [
            b for (s, b), rs in by_brief.items() if s == style and any(not r["exact"] for r in rs)
        ]
        total = len({b for (s, b) in by_brief if s == style})
        lines.append(
            f"- **{style}**: {len(induced)}/{total} briefs induziram ao menos uma implementação errada"
        )
        for brief_id in sorted(induced):
            fams = Counter(family_of(d) for r in by_brief[(style, brief_id)] for d in r["diffs"])
            arms_bad = [r["arm"] for r in by_brief[(style, brief_id)] if not r["exact"]]
            top = ", ".join(f"{k} ×{v}" for k, v in fams.most_common(3)) or "erro de construção"
            lines.append(f"  - `{brief_id}` ({'+'.join(arms_bad)}): {top}")

    families = Counter(family_of(d) for r in rows for d in r["diffs"])
    if families:
        lines += ["", "## Famílias de erro (todas as divergências)", ""]
        for name, n in families.most_common():
            lines.append(f"- {name}: {n}")

    report = "\n".join(lines) + "\n"
    (results_dir / f"{args.round}.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
