"""The token guard in conftest.py: no test sees a real token.

The probe runs in a fresh pytest with all five tokens exported to
real-looking values and the repository's conftest loaded as a plugin; it
passes only when the guard removed every one of them, so this test fails
when the guard is removed.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

FAKE = {
    "CICD_WRITE_TOKEN": "ghp_FAKEwrite0123456789abcdefABCDEF0123",
    "CICD_READ_TOKEN": "ghp_FAKEread0123456789abcdefABCDEF01234",
    "VENDOR_PAT": "github_pat_FAKE0123456789abcdefABCDEF",
    "GH_TOKEN": "gho_FAKE0123456789abcdefABCDEF012345678",
    "GITHUB_TOKEN": "ghs_FAKE0123456789abcdefABCDEF01234567",
}

PROBE = '''
import os

NAMES = {names!r}


def test_probe_sees_no_token():
    seen = [n for n in NAMES if n in os.environ]
    assert seen == [], "tokens visible to a test: " + ", ".join(seen)
'''


def test_probe_sees_no_token_exported_outside(tmp_path):
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE.format(names=sorted(FAKE)))
    env = dict(os.environ, **FAKE)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "-p", "tests.conftest", "--rootdir", str(tmp_path), str(probe)],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
