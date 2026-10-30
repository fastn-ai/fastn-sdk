"""Release hygiene: the version and the generated type stub must match the package."""
import re
import subprocess
import sys
from pathlib import Path

import fastn

PY_ROOT = Path(__file__).resolve().parents[2]


def test_version_matches_pyproject() -> None:
    m = re.search(r'^version = "([^"]+)"', (PY_ROOT / "pyproject.toml").read_text(), re.M)
    assert m and m.group(1) == fastn.__version__


def test_client_stub_is_up_to_date() -> None:
    r = subprocess.run(
        [sys.executable, str(PY_ROOT / "scripts" / "generate_client_stub.py"), "--check"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
