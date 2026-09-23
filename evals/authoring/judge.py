"""Judge for the authoring eval: loads an agent's ontology file, derives its IR
(``ontology.model_dump()``) and diffs it against the task's gold IR.

Must run with the spike branch's tank package importable, e.g.:

    cd ../tank-spike && uv run python \
        ../tank/evals/authoring/judge.py \
        --run-id T1--typed--r1 --arm typed --task 1 <submission.py>

Every invocation is logged; the scorer reads the log (iterations, first-try
construction, arm violations), never the agent's self-report. At most
MAX_SUBMISSIONS judged submissions per run.
"""

import argparse
import importlib.util
import json
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).parent
MAX_SUBMISSIONS = 6
MAX_DIFFS_SHOWN = 12


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def legacy_stamp(name: str, version: str):
    """Fill in `Ontology.name`/`version` for submissions written before they existed.

    The committed submissions are *experiment data*: they are what agents
    actually wrote, under the prompts of their round. Editing 137 files to
    satisfy a validator that shipped later would silently rewrite the record,
    and the corpus would stop being evidence of anything. So the shim lives
    here, fills in only the missing pair, and every judged result records
    whether it fired (`stamp_injected`). A submission that sets them itself is
    left alone.
    """
    from tank import Ontology

    original = Ontology.__init__
    fired: list[bool] = []

    def patched(self, *args, **kwargs):
        fired.append(any(k not in kwargs for k in ("name", "version")))
        kwargs.setdefault("name", name)
        kwargs.setdefault("version", version)
        original(self, *args, **kwargs)

    Ontology.__init__ = patched
    try:
        yield fired
    finally:
        Ontology.__init__ = original


def normalize(dump: dict) -> dict:
    """Sort every named collection so declaration order never counts as a diff.

    The stamp is dropped: it is not part of what the eval asks an agent to get
    right, and leaving it in would make every shimmed submission match the gold
    on two fields it never wrote.
    """
    out = json.loads(json.dumps(dump, default=str))
    out.pop("name", None)
    out.pop("version", None)
    out["types"] = sorted(out.get("types") or [], key=lambda t: t["name"])
    for unit_type in out["types"]:
        unit_type["attrs"] = sorted(unit_type.get("attrs") or [], key=lambda a: a["name"])
    out["relations"] = sorted(out.get("relations") or [], key=lambda r: r["name"])
    out["scopes"] = sorted(out.get("scopes") or [], key=lambda s: s["name"])
    out["freshness"] = sorted(
        out.get("freshness") or [], key=lambda f: (f["unit_type"], f["field"])
    )
    return out


def flatten(node, prefix="", out=None) -> dict:
    if out is None:
        out = {}
    if isinstance(node, dict):
        for key, value in node.items():
            flatten(value, f"{prefix}.{key}" if prefix else key, out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            flatten(value, f"{prefix}[{i}]", out)
    else:
        out[prefix] = node
    return out


def diff(gold: dict, got: dict) -> list[str]:
    gold_flat, got_flat = flatten(gold), flatten(got)
    lines = []
    for path in sorted(set(gold_flat) | set(got_flat)):
        if path not in got_flat:
            lines.append(f"missing: {path} (expected {gold_flat[path]!r})")
        elif path not in gold_flat:
            lines.append(f"unexpected: {path} = {got_flat[path]!r}")
        elif gold_flat[path] != got_flat[path]:
            lines.append(f"differs: {path} = {got_flat[path]!r}, expected {gold_flat[path]!r}")
    return lines


def check_arm(module, arm: str) -> str | None:
    from tank import Edge, Unit

    typed_classes = [
        v
        for v in vars(module).values()
        if isinstance(v, type) and issubclass(v, (Unit, Edge)) and v not in (Unit, Edge)
    ]
    if arm == "typed" and not typed_classes:
        return "arm violation: the typed arm must declare Unit/Edge subclasses"
    if arm == "declarative" and typed_classes:
        return "arm violation: the declarative arm must not declare Unit/Edge subclasses"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--arm", required=True, choices=["declarative", "typed"])
    parser.add_argument("--task", required=True, type=int, choices=[1, 2, 3, 4])
    parser.add_argument("--round", default="round1")
    parser.add_argument("submission")
    args = parser.parse_args()

    log_dir = HERE / "runs" / args.round / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{args.run_id}.jsonl"
    prior = len(log_path.read_text().splitlines()) if log_path.exists() else 0

    def emit(entry: dict) -> None:
        record = {"ts": time.time(), "run_id": args.run_id, "arm": args.arm, "task": args.task}
        record.update(entry)
        with log_path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        print(json.dumps({k: v for k, v in entry.items() if k != "refused_budget"}, indent=1))

    if prior >= MAX_SUBMISSIONS:
        emit(
            {
                "constructs": False,
                "exact": False,
                "error": f"BUDGET EXHAUSTED: at most {MAX_SUBMISSIONS} submissions per run",
                "refused_budget": True,
            }
        )
        return 1

    result = {"constructs": False, "arm_ok": True, "exact": False, "diff_count": None}
    try:
        with legacy_stamp(f"submission_{args.run_id}", "0") as injected:
            module = load_module(Path(args.submission), f"submission_{args.run_id}_{prior}")
        result["stamp_injected"] = any(injected)
        from tank import Ontology

        ontology = getattr(module, "ontology", None)
        if not isinstance(ontology, Ontology):
            raise TypeError("module must expose a module-level `ontology` (a tank Ontology)")
        result["constructs"] = True
        violation = check_arm(module, args.arm)
        if violation:
            result["arm_ok"] = False
            result["error"] = violation
        gold_module = load_module(HERE / "golds" / f"task{args.task}.py", f"gold{args.task}")
        gold = normalize(gold_module.build().model_dump())
        got = normalize(ontology.model_dump())
        lines = diff(gold, got)
        result["diff_count"] = len(lines)
        result["exact"] = not lines and result["arm_ok"]
        if lines:
            result["diffs"] = lines[:MAX_DIFFS_SHOWN]
            if len(lines) > MAX_DIFFS_SHOWN:
                result["diffs"].append(f"... and {len(lines) - MAX_DIFFS_SHOWN} more")
    except Exception:  # noqa: BLE001 — any submission failure must become a judged result
        result["error"] = traceback.format_exc(limit=3)[-1500:]

    emit(result)
    return 0 if result["exact"] else 1


if __name__ == "__main__":
    main()
