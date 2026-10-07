import copy
import pytest

from ai_checkpoint import GitStore

VALID = {
    "chat_name": "forecasting",
    "checkpoint_name": "v1",
    "objective": "Build a demand forecast",
    "context": "Weekly data, 3 years",
    "decisions": [{"decision": "Use Prophet", "reason": "handles seasonality"}],
    "completed": ["Loaded data"],
    "current_step": "Tuning changepoints",
    "next_steps": ["Run backtest", "Write report"],
    "open_questions": ["Which holidays?"],
    "verbatim": [{"label": "model", "content": "m = Prophet(changepoint_prior_scale=0.05)\n"}],
    "last_exchange": {"user": "go on", "assistant": "ok"},
    "notes_for_next_ai": "User prefers terse answers",
    "client": "claude-code",
}


@pytest.fixture
def valid():
    return copy.deepcopy(VALID)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never touch the real home: HOME and AI_CHECKPOINT_HOME point into tmp."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AI_CHECKPOINT_HOME", raising=False)
    # No global git identity/config at all.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return home


@pytest.fixture
def root(tmp_path):
    return tmp_path / "store"


@pytest.fixture
def store(root):
    return GitStore(root)
