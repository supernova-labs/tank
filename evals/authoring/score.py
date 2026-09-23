"""Score the authoring eval from the judge logs (the agent's self-report is
ignored except for `gave_up`).

Per run: success (any judged submission exact), submissions used, first-try
construction, first-try exactness, arm violations. Matrix: arm x task.

Usage: uv run python evals/authoring/score.py [--round round1] [--raw results/round1_raw.json]
"""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", default="round1")
    parser.add_argument("--raw", default=None, help="agent structured outputs (for gave_up only)")
    args = parser.parse_args()

    round_dir = HERE / "runs" / args.round
    manifest = json.loads((round_dir / "manifest.json").read_text())
    gave_up = {}
    if args.raw:
        for r in json.loads(Path(args.raw).read_text()):
            if r:
                gave_up[r.get("run_id")] = bool(r.get("gave_up"))

    scored = []
    for meta in manifest:
        log_path = round_dir / "log" / f"{meta['run_id']}.jsonl"
        entries = (
            [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
            if log_path.exists()
            else []
        )
        judged = [e for e in entries if not e.get("refused_budget")]
        scored.append(
            {
                **meta,
                "submissions": len(judged),
                "success": any(e.get("exact") for e in judged),
                "first_constructs": bool(judged) and bool(judged[0].get("constructs")),
                "first_exact": bool(judged) and bool(judged[0].get("exact")),
                "first_diffs": judged[0].get("diff_count") if judged else None,
                "arm_violation": any(e.get("arm_ok") is False for e in judged),
                "gave_up": gave_up.get(meta["run_id"], False),
                "never_submitted": not judged,
            }
        )

    results_dir = HERE / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / f"{args.round}_scored.json").write_text(json.dumps(scored, indent=2))

    cells = defaultdict(list)
    for row in scored:
        cells[(row["arm"], row.get("model", "sonnet"), row["task"])].append(row)
    arms = list(dict.fromkeys((m["arm"], m.get("model", "sonnet")) for m in manifest))
    many_models = len({model for _, model in arms}) > 1
    tasks = sorted({m["task"] for m in manifest})

    lines = [f"# Authoring eval {args.round} — arm x task", ""]
    lines.append(
        "Cell: `success/total · mediana de submissões · exact de primeira/total "
        "(diffs medianos na 1a tentativa)`"
    )
    lines.append("")
    lines.append("| arm | " + " | ".join(f"T{t}" for t in tasks) + " |")
    lines.append("|---" * (len(tasks) + 1) + "|")
    for arm, model in arms:
        row = [f"{arm} ({model})" if many_models else arm]
        for task in tasks:
            runs = cells.get((arm, model, task), [])
            if not runs:
                row.append("—")
                continue
            ok = sum(r["success"] for r in runs)
            med_sub = statistics.median(r["submissions"] for r in runs)
            first = sum(r["first_exact"] for r in runs)
            fdiffs = [r["first_diffs"] for r in runs if r["first_diffs"] is not None]
            fd = statistics.median(fdiffs) if fdiffs else "—"
            row.append(f"{ok}/{len(runs)} · {med_sub:g}s · 1a:{first}/{len(runs)} ({fd}d)")
        lines.append("| " + " | ".join(row) + " |")

    problems = [r for r in scored if r["arm_violation"] or r["never_submitted"] or not r["success"]]
    if problems:
        lines += ["", "## Runs com problema", ""]
        for r in problems:
            what = []
            if not r["success"]:
                what.append("não chegou a exact")
            if r["arm_violation"]:
                what.append("violação de braço")
            if r["never_submitted"]:
                what.append("nunca submeteu")
            lines.append(f"- `{r['run_id']}`: {', '.join(what)} ({r['submissions']} submissões)")

    report = "\n".join(lines) + "\n"
    (results_dir / f"{args.round}.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
