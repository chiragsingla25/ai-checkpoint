"""``checkpoint-eval`` command line."""
from __future__ import annotations

import argparse
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from ..errors import CheckpointError
from .generate import generate_dataset
from .models import DEFAULT_MODELS, DEFAULT_TIMEOUT, MODEL_CHOICES, MODEL_ENV, make_model
from .pipeline import run_scenario
from .report import markdown_table, write_outputs
from .scenario import load_scenario


def _positive(text: str) -> float:
    try:
        v = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not v > 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return v


def _workers(text: str) -> int:
    try:
        v = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if v < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return v


def _common(r: argparse.ArgumentParser) -> None:
    r.add_argument("--model", choices=MODEL_CHOICES, default="fake",
                   help="fake (offline, deterministic; default), anthropic or openai "
                   "(openai honours OPENAI_BASE_URL, e.g. OpenRouter)")
    r.add_argument("--model-name", default=None,
                   help="model id for anthropic/openai (defaults: "
                   + ", ".join(f"{k}={v}" for k, v in DEFAULT_MODELS.items())
                   + "; env overrides: " + ", ".join(MODEL_ENV.values()) + ")")
    r.add_argument("--timeout", type=_positive, default=DEFAULT_TIMEOUT,
                   help="seconds allowed per model call; a failed or timed-out call is retried once "
                   f"(default {DEFAULT_TIMEOUT:g})")
    r.add_argument("--workers", type=_workers, default=8, metavar="N",
                   help="maximum model calls in flight at once, across all scenarios (default 8; 1 = fully sequential)")
    r.add_argument("--force", action="store_true",
                   help="replace an existing results.json in the output folder (default: refuse)")
    r.add_argument("--strict-next-step", action="store_true", dest="strict_next_step",
                   help="score next-step answers by literal required terms (default: a filename term "
                   "also matches its stem or number, e.g. 'migration 0023')")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="checkpoint-eval",
        description="Compare handover quality: checkpoint brief vs plain summary vs full history.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run one scenario and write results.json and results.md")
    r.add_argument("scenario", help="scenario JSON file (see examples/scenarios/)")
    _common(r)
    r.add_argument("--out", required=True, help="output directory (created if missing)")
    st = sub.add_parser("suite", help="run several scenarios; one folder per scenario under --out")
    st.add_argument("scenarios", nargs="+", help="scenario JSON files, e.g. datasets/handover-v1/*.json")
    _common(st)
    st.add_argument("--out", required=True, help="output directory; results go to OUT/<scenario-name>/")
    rs = sub.add_parser("rescore", help="recompute the code-scored metrics of a finished run from its saved "
                        "answers (no model call; results.json is not modified)")
    rs.add_argument("results_dir", help="a results folder, or a folder of scenario folders, containing results.json files")
    rs.add_argument("--dataset", default="datasets/handover-v1",
                    help="folder with the scenario files named by results.json 'scenario' (default datasets/handover-v1)")
    rs.add_argument("--strict-next-step", action="store_true", dest="strict_next_step",
                    help="literal required terms for next-step scoring")
    g = sub.add_parser("generate", help="generate the handover dataset (6 scenario files; no model needed)")
    g.add_argument("--seed", type=int, default=7, help="integer seed (default 7; the committed dataset uses 7)")
    g.add_argument("--out", required=True, help="output directory (created if missing)")
    return p


def _generate(args) -> int:
    out = Path(args.out)
    if out.exists() and not out.is_dir():
        print(f"error: --out {out} exists and is not a directory", file=sys.stderr)
        return 1
    try:
        paths = generate_dataset(args.seed, out)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for p in paths:
        print(p)
    return 0


def _exists_error(folder: Path) -> str:
    return f"error: {folder / 'results.json'} already exists; use --force to replace it"


def _run_one(scenario, model, folder: Path, timeout: float, workers: int = 1, limiter=None,
             strict_next_step: bool = False) -> str:
    results = run_scenario(scenario, model, timeout=timeout, progress=sys.stderr, workers=workers, limiter=limiter,
                           strict_next_step=strict_next_step)
    write_outputs(results, folder)
    return markdown_table(results)


def _run(args) -> int:
    out = Path(args.out)
    try:
        scenario = load_scenario(args.scenario)
        if (out / "results.json").exists() and not args.force:
            print(_exists_error(out), file=sys.stderr)
            return 1
        model = make_model(args.model, args.model_name, args.timeout)
        table = _run_one(scenario, model, out, args.timeout, args.workers, strict_next_step=args.strict_next_step)
    except (CheckpointError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(table, end="")
    return 0


def _suite(args) -> int:
    out = Path(args.out)
    try:
        scenarios = [load_scenario(p) for p in args.scenarios]
        names = [s.name for s in scenarios]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            print(f"error: duplicate scenario name(s): {', '.join(dupes)}", file=sys.stderr)
            return 1
        if not args.force:
            clash = [out / n for n in names if (out / n / "results.json").exists()]
            if clash:
                print(_exists_error(clash[0]) + (f" (and {len(clash) - 1} more)" if len(clash) > 1 else ""),
                      file=sys.stderr)
                return 1
        model = make_model(args.model, args.model_name, args.timeout)
    except (CheckpointError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    failed = 0
    limiter = threading.BoundedSemaphore(args.workers) if args.workers > 1 else None
    with ThreadPoolExecutor(max_workers=len(scenarios) if args.workers > 1 else 1) as ex:
        # sequential (workers=1) runs each scenario inline in order; otherwise scenarios start together
        # and share the limiter; results are reported in command-line order either way
        futs = [ex.submit(_run_one, sc, model, out / sc.name, args.timeout, args.workers, limiter, args.strict_next_step)
                for sc in scenarios]
        for i, (sc, fut) in enumerate(zip(scenarios, futs)):
            try:
                table = fut.result()
            except (CheckpointError, OSError) as e:
                print(f"error: scenario {sc.name}: {e}", file=sys.stderr)
                failed += 1
                continue
            if i:
                print()
            print(table, end="")
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        return _generate(args)
    if args.command == "rescore":
        from .rescore import rescore_command
        return rescore_command(args.results_dir, args.dataset, args.strict_next_step)
    if args.command == "suite":
        return _suite(args)
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
