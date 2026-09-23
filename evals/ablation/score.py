"""Score one ablation round: agent outputs vs gold, query logs as ground truth
for cost and rule violations.

Usage: uv run python evals/ablation/score.py --raw results/round1_raw.json [--round round1] [--spec spec_round1]
"""

import argparse
import importlib
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
INTROSPECT = re.compile(r"^\s*(INFO|DESCRIBE|SHOW)\b", re.IGNORECASE | re.MULTILINE)


def norm_key(record_id: str) -> str:
    """'article:⟨a1⟩' / 'article:a1' / 'a1' → 'a1' (keys are unique across tables)."""
    tail = str(record_id).strip().strip("`").split(":")[-1]
    return re.sub(r"[^A-Za-z0-9_]", "", tail).lower()


def is_correct(task: dict, result: dict) -> bool:
    if task["kind"] == "count":
        return result.get("answer_count") == task["gold"]
    answered = [norm_key(x) for x in result.get("answer_ids") or []]
    gold = [norm_key(x) for x in task["gold"]]
    if task["kind"] == "id_list":
        return answered == gold
    return set(answered) == set(gold) and len(answered) == len(gold)


def read_log(round_dir: Path, run_id: str) -> list[dict]:
    path = round_dir / "log" / f"{run_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, help="JSON array of agent structured outputs")
    parser.add_argument("--round", default="round1")
    parser.add_argument("--spec", default="spec_round1")
    args = parser.parse_args()

    by_task_id = {t["id"]: t for t in importlib.import_module(args.spec).TASKS}
    round_dir = HERE / "runs" / args.round
    manifest = {m["run_id"]: m for m in json.loads((round_dir / "manifest.json").read_text())}
    raw = json.loads(Path(args.raw).read_text())
    by_run = {r["run_id"]: r for r in raw if r and r.get("run_id") in manifest}

    scored = []
    for run_id, meta in manifest.items():
        task = by_task_id[meta["task"]]
        result = by_run.get(run_id)
        entries = read_log(round_dir, run_id)
        queries = len(entries)
        errors = sum(1 for e in entries if not e["ok"] and not e.get("refused"))
        refused = sum(1 for e in entries if e.get("refused"))
        violation = meta["condition"] == "nointro" and any(
            e["allow_introspect"] and INTROSPECT.match(e["sql"]) for e in entries
        )
        scored.append(
            {
                **meta,
                "answered": result is not None,
                "correct": bool(result) and not violation and is_correct(task, result),
                "gave_up": bool(result and result.get("gave_up")),
                "queries": queries,
                "errors": errors,
                "refused": refused,
                "violation": violation,
            }
        )

    results_dir = HERE / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / f"{args.round}_scored.json").write_text(json.dumps(scored, indent=2))

    # ---- aggregate: variant x condition x category -------------------------------
    cells = defaultdict(list)
    for row in scored:
        cells[(row["variant"], row["condition"], row["category"])].append(row)

    variants = list(dict.fromkeys(m["variant"] for m in manifest.values()))
    categories = list(dict.fromkeys(m["category"] for m in manifest.values()))
    conditions = list(dict.fromkeys(m["condition"] for m in manifest.values()))

    lines = [f"# Ablation {args.round} — scored matrix", ""]
    lines.append("Cell format: `correct/total (median queries)`.")
    for condition in conditions:
        lines += ["", f"## Condition: {condition}", ""]
        lines.append("| variant | " + " | ".join(categories) + " |")
        lines.append("|---" * (len(categories) + 1) + "|")
        for variant in variants:
            row = [variant]
            for category in categories:
                runs = cells.get((variant, condition, category), [])
                if not runs:
                    row.append("—")
                    continue
                ok = sum(r["correct"] for r in runs)
                med_q = statistics.median(r["queries"] for r in runs)
                row.append(f"{ok}/{len(runs)} ({med_q:g}q)")
            lines.append("| " + " | ".join(row) + " |")

    problems = [r for r in scored if not r["answered"] or r["violation"]]
    if problems:
        lines += ["", "## Anomalies", ""]
        for r in problems:
            what = "no structured output" if not r["answered"] else "introspection violation"
            lines.append(f"- `{r['run_id']}`: {what}")

    report = "\n".join(lines) + "\n"
    (results_dir / f"{args.round}.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
