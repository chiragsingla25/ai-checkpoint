"""Handover evaluation kit: checkpoint brief vs plain summary vs full history.

Stdlib only; the Anthropic/OpenAI SDKs are imported lazily by their adapters.
Run with ``checkpoint-eval run SCENARIO.json --model fake --out DIR``.
"""
from .models import FakeModel, Model, ModelError, make_model
from .pipeline import VARIANTS, run_scenario
from .scenario import Probe, Scenario, ScenarioError, load_scenario, parse_scenario

__all__ = [
    "Model", "FakeModel", "ModelError", "make_model",
    "Scenario", "Probe", "ScenarioError", "load_scenario", "parse_scenario",
    "run_scenario", "VARIANTS",
]
