"""``checkpoint-eval`` command line."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from ..errors import CheckpointError
from .generate import generate_dataset
from .models import DEFAULT_MODELS, MODEL_CHOICES, MODEL_ENV, make_model
from .pipeline import run_scenario
from .report import markdown_table, write_outputs
from .scenario import load_scenario


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="checkpoint-eval",
        description="Compare handover quality: checkpoint brief vs plain summary vs full history.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run one scenario and write results.json and results.md")
    r.add_argument("scenario", help="scenario JSON file (see examples/scenarios/)")
    r.add_argument("--model", choices=MODEL_CHOICES, default="fake",
                   help="fake (offline, deterministic; default), anthropic or openai")
    r.add_argument("--model-name", default=None,
                   help="model id for anthropic/openai (defaults: "
                   + ", ".join(f"{k}={v}" for k, v in DEFAULT_MODELS.items())
                   + "; env overrides: " + ", ".join(MODEL_ENV.values()) + ")")
    r.add_argument("--out", required=True, help="output directory (created if missing)")
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


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        return _generate(args)
    try:
        scenario = load_scenario(args.scenario)
        model = make_model(args.model, args.model_name)
        results = run_scenario(scenario, model)
        write_outputs(results, args.out)
    except CheckpointError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(markdown_table(results), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
