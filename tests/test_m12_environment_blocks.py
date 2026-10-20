import json
from types import SimpleNamespace
import unittest

from runner.agents.codex import CodexAdapter
from runtime import (
    JobState,
    RuntimeEventBridge,
    ReactiveJobEngine,
    TaskExecutionResult,
    TaskNode,
    VerificationResult,
    VerificationStatus,
)
from tests.test_phase8_reactive_runtime import create_test_capability_registry


class TestParserEnvironmentBlock(unittest.TestCase):
    def test_json_environment_block_is_terminal_signal(self):
        out = json.dumps({"verdict": "failed", "summary": "no net", "blocked_by": "environment", "repairable": True})
        parsed = CodexAdapter.parse_verification_output(out)
        self.assertEqual(parsed["blocked_by"], "environment")
        self.assertFalse(parsed["repairable"])
        self.assertFalse(parsed["trigger_replan"])
        self.assertFalse(parsed["observations"][0]["metadata"]["requires_follow_up"])

    def test_text_environment_block(self):
        parsed = CodexAdapter.parse_verification_output("VERDICT: FAIL\nSUMMARY: ro fs\nBLOCKED_BY: environment\n")
        self.assertEqual(parsed["blocked_by"], "environment")
        self.assertFalse(parsed["repairable"])
        self.assertFalse(parsed["observations"][0]["metadata"]["requires_follow_up"])

    def test_real_defect_is_still_repairable(self):
        out = json.dumps({"verdict": "failed", "summary": "bug", "blocked_by": None})
        parsed = CodexAdapter.parse_verification_output(out)
        self.assertIsNone(parsed["blocked_by"])
        self.assertTrue(parsed["repairable"])
        self.assertTrue(parsed["trigger_replan"])
        self.assertTrue(parsed["observations"][0]["metadata"]["requires_follow_up"])

    def test_text_none_is_not_blocked(self):
        parsed = CodexAdapter.parse_verification_output("VERDICT: FAIL\nBLOCKED_BY: none\n")
        self.assertNotEqual(parsed["blocked_by"], "environment")
        self.assertTrue(parsed["repairable"])

    def test_verification_result_roundtrip_keeps_blocked_by(self):
        res = VerificationResult(status=VerificationStatus.REPAIRABLE, summary="x", blocked_by="environment")
        self.assertFalse(res.is_repairable)
        self.assertEqual(VerificationResult.from_dict(res.to_dict()).blocked_by, "environment")


class TestEngineEnvironmentBlock(unittest.IsolatedAsyncioTestCase):
    async def _run(self, metadata):
        planned = []

        class Planner:
            async def plan(self, *a, **k):
                planned.append(1)
                raise AssertionError("replan must not happen")

        engine = ReactiveJobEngine(
            job_id="job_m12",
            goal="g",
            capability_registry=create_test_capability_registry(),
            event_bridge=RuntimeEventBridge(),
        )

        async def adapter(task, run, ctx):
            return TaskExecutionResult(status="failed", error="v", metadata=metadata)

        engine.set_default_execution_adapter(adapter)
        await engine.initialize_and_plan(initial_tasks=[
            TaskNode(task_id="V1", job_id="job_m12", description="verify", required_capabilities=["repo.read"])
        ])
        await engine.step()
        return engine

    async def test_task_level_environment_block_ends_job_blocked(self):
        engine = await self._run({"verdict": "failed", "blocked_by": "environment", "verification_summary": "ro fs"})
        self.assertEqual(engine.state, JobState.BLOCKED)

    async def test_task_level_repairable_verdict_does_not_block(self):
        engine = await self._run({"verdict": "failed", "repairable": True})
        self.assertNotEqual(engine.state, JobState.BLOCKED)


class TestVerifierEnvironmentBlock(unittest.IsolatedAsyncioTestCase):
    async def test_verifier_environment_block_ends_job(self):
        async def verifier(job, graph, arts, ctx):
            return VerificationResult(status=VerificationStatus.REPAIRABLE, summary="ro", blocked_by="environment")

        engine = ReactiveJobEngine(
            job_id="job_m12v", goal="g",
            capability_registry=create_test_capability_registry(),
            event_bridge=RuntimeEventBridge(), verifier=verifier,
        )

        async def ok(task, run, ctx):
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(ok)
        await engine.initialize_and_plan(initial_tasks=[
            TaskNode(task_id="T1", job_id="job_m12v", description="d", required_capabilities=["repo.read"])
        ])
        final = await engine.run_until_complete()
        self.assertEqual(final.state, JobState.BLOCKED)
        self.assertEqual(final.repair_count, 0)


class TestHermesVerifierAdapterClassification(unittest.IsolatedAsyncioTestCase):
    async def _verify(self, steps):
        import tempfile
        from pathlib import Path
        from runtime.hermes_adapter import HermesVerifierAdapter

        with tempfile.TemporaryDirectory() as tmp:
            adapter = HermesVerifierAdapter(verification_steps=steps, working_dir=Path(tmp))
            return await adapter.verify(job=SimpleNamespace(job_id='j'), graph=None, artifacts=[])

    async def test_real_failure_is_repairable_not_blocked(self):
        res = await self._verify([{"name": "t", "command": ["sh", "-c", "echo bug >&2; exit 1"]}])
        self.assertEqual(res.status, VerificationStatus.REPAIRABLE)
        self.assertIsNone(res.blocked_by)
        self.assertTrue(res.is_repairable)

    async def test_environment_failure_is_blocked(self):
        res = await self._verify([{"name": "t", "command": ["sh", "-c", "echo 'EPERM: operation not permitted' >&2; exit 1"]}])
        self.assertEqual(res.blocked_by, "environment")
        self.assertFalse(res.is_repairable)

    async def test_environment_block_does_not_hide_real_defect(self):
        res = await self._verify([
            {"name": "env", "command": ["sh", "-c", "echo 'permission denied' >&2; exit 1"]},
            {"name": "bug", "command": ["sh", "-c", "echo assertion failed >&2; exit 1"]},
        ])
        self.assertIsNone(res.blocked_by)
        self.assertTrue(res.is_repairable)

    async def test_sandbox_word_alone_is_not_environment(self):
        res = await self._verify([{"name": "t", "command": ["sh", "-c", "echo 'sandbox test failed' >&2; exit 1"]}])
        self.assertIsNone(res.blocked_by)


if __name__ == "__main__":
    unittest.main()
