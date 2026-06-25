"""Test fixtures: isolated $WS_HOME + in-process invocation helper."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ws  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolate storage in a temporary WS_HOME and neutralize XDG."""
    h = tmp_path / "wshome"
    monkeypatch.setenv("WS_HOME", str(h))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdgdata"))
    monkeypatch.setenv("XDG_BIN_HOME", str(tmp_path / "bin"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("WS_COLOR", raising=False)
    return h


@pytest.fixture
def run(capsys):
    """Invoke the CLI in-process; returns (code, stdout, stderr)."""
    def _run(*args):
        try:
            code = ws.main([str(a) for a in args])
        except SystemExit as exc:  # argparse → usage errors
            code = exc.code if isinstance(exc.code, int) else 1
        out = capsys.readouterr()
        return code, out.out, out.err
    return _run


@pytest.fixture
def mkdirs(tmp_path):
    """Create real folders and return their absolute paths."""
    def _mk(*names):
        paths = []
        for n in names:
            d = tmp_path / n
            d.mkdir(parents=True, exist_ok=True)
            paths.append(str(d))
        return paths
    return _mk
