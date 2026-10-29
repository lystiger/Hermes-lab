"""A job whose project declares no checks is not verified by default: it blocks until checks exist."""
from types import SimpleNamespace

import pytest

from runtime.hermes_adapter import HermesVerifierAdapter


async def verify(tmp_path, **kwargs):
    (tmp_path / "integration").mkdir()
    verifier = HermesVerifierAdapter(verification_steps=[], working_dir=tmp_path, worktree_root=tmp_path, **kwargs)
    return await verifier.verify(job=SimpleNamespace(job_id="j"), graph=None, artifacts=[])


@pytest.mark.anyio
async def test_no_checks_blocks_the_job(tmp_path):
    result = await verify(tmp_path)
    assert not result.is_passed
    assert result.blocked_by == "environment"
    assert "hermes.json" in result.summary


@pytest.mark.anyio
async def test_a_dry_run_without_checks_still_passes(tmp_path):
    result = await verify(tmp_path, allow_unchecked=True)
    assert result.is_passed
