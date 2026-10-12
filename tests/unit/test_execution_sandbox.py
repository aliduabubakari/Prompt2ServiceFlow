"""Generated runtime code must not escape its execution sandbox."""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

import pytest

from prompt2serviceflow.validators.instance_validation import _run_generated_task


STRONG_SANDBOX_AVAILABLE = (
    platform.system() == "Darwin" and shutil.which("sandbox-exec") is not None
) or shutil.which("docker") is not None


@pytest.mark.skipif(not STRONG_SANDBOX_AVAILABLE, reason="strong sandbox unavailable")
def test_generated_script_cannot_read_repository(tmp_path: Path) -> None:
    instance = tmp_path / "instance"
    runtime = instance / "runtime" / "scripts"
    fixtures = instance / "fixtures" / "inputs"
    workspace = tmp_path / "scenario"
    runtime.mkdir(parents=True)
    fixtures.mkdir(parents=True)
    workspace.mkdir()
    protected = Path(__file__).resolve().parents[2] / "README.md"
    (runtime / "escape.py").write_text(
        f"from pathlib import Path\nprint(Path({str(protected)!r}).read_text())\n",
        encoding="utf-8",
    )
    completed = _run_generated_task(
        instance_dir=instance,
        script="scripts/escape.py",
        arguments=[],
        fixtures=fixtures,
        workspace=workspace,
        timeout_seconds=10,
    )
    assert completed.returncode != 0
    assert "Operation not permitted" in completed.stderr or "PermissionError" in completed.stderr
