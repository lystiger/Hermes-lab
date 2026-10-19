from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import asyncio
import httpx

import agent_models
from agent_models import ModelRegistry
from main import app


class TestClient:
    __test__ = False

    def __init__(self, app):
        self.app = app

    def request(self, method, path, **kwargs):
        async def perform():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver") as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(perform())

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def options(self, path, **kwargs):
        return self.request("OPTIONS", path, **kwargs)


def test_api_validation_roundtrip_and_agent_source():
    registry = agent_models.model_registry
    client = TestClient(app)
    assert client.put('/agents/missing/model', json={'model': 'sonnet'}).status_code == 404
    assert client.put('/agents/claude/model', json={'model': '--evil'}).status_code == 400
    assert client.put('/agents/claude/model', json={'model': 'opus', 'effort': 'high'}).status_code == 400
    assert not registry.path.exists()
    response = client.put('/agents/claude/model', json={'model': 'opus'})
    assert response.status_code == 200
    assert response.json() == {'default': 'opus', 'effort': None}
    fresh = ModelRegistry(registry.path, registry.codex_path)
    assert fresh.configured('claude')['default'] == 'opus'
    models = client.get('/agents/models').json()
    assert models['claude']['configured']['default'] == 'opus'
    assert models['claude']['lastUsed'] is None
    summaries = {a['id']: a for a in client.get('/agents').json()}
    assert summaries['claude']['model'] == 'opus'
    assert summaries['codex']['model'] is None
    assert client.put('/agents/gemini/model', json={'model': '--evil'}).status_code == 400


def test_cors_put():
    response = TestClient(app).options('/agents/codex/model', headers={
        'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'PUT'})
    assert response.status_code == 200
    assert 'PUT' in response.headers['access-control-allow-methods']


def test_codex_config_and_precedence():
    registry = agent_models.model_registry
    registry.codex_path.write_text('model = "local-model"\nmodel_reasoning_effort = "high"\n')
    assert 'local-model' in registry.allowed('codex')
    assert registry.resolve('codex', {}) == {'model': 'local-model', 'effort': 'high', 'source': 'config'}
    registry.set('codex', 'gpt-5-codex', 'medium')
    assert registry.resolve('codex', {})['model'] == 'gpt-5-codex'
    assert registry.resolve('codex', {'model': 'phase-model', 'effort': 'low'}) == {
        'model': 'phase-model', 'effort': 'low', 'source': 'phase'}
    assert registry.resolve('claude', {}) == {'model': None, 'effort': None, 'source': 'cli-default'}


def test_agy_fake_cli_and_cache(tmp_path, monkeypatch):
    cli = tmp_path / 'agy'
    cli.write_text('#!/bin/sh\nprintf "id\\tname\\nmodel-a\\tAlpha\\nmodel-b\\tBeta\\n"\n')
    cli.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path))
    registry = agent_models.model_registry
    assert registry.allowed('gemini') == ['model-a', 'model-b']
    cli.unlink()
    assert registry.allowed('antigravity') == ['model-a', 'model-b']
    registry._cache = (0, [])
    assert registry.allowed('antigravity') == ['gemini-2.5-pro', 'gemini-2.5-flash']


def test_atomic_write_failure_preserves_previous(monkeypatch):
    registry = agent_models.model_registry
    registry.set('claude', 'sonnet', None)
    original = registry.path.read_bytes()
    def fail(*args):
        raise OSError('replace failed')
    monkeypatch.setattr(agent_models.os, 'replace', fail)
    with pytest.raises(OSError, match='replace failed'):
        registry.set('claude', 'opus', None)
    assert registry.path.read_bytes() == original
    assert sorted(p.name for p in registry.path.parent.glob('agent_models.json.*')) == []


def test_adapters_commands_and_event_metadata(tmp_path, monkeypatch):
    from agents import base
    from agents.codex import CodexAdapter
    from agents.claude import ClaudeAdapter
    from agents.antigravity import AntigravityAdapter
    registry = agent_models.model_registry
    registry.set('codex', 'gpt-5-codex', 'high')
    adapter = CodexAdapter()
    command = adapter.build_command('work', {})
    assert command[command.index('--model') + 1] == 'gpt-5-codex'
    assert 'model_reasoning_effort="high"' in command
    assert '--model' not in ClaudeAdapter().build_command('work', {})
    registry.set('claude', 'haiku', None)
    assert 'haiku' in ClaudeAdapter().build_command('work', {})
    registry._cache = (agent_models.time.monotonic(), ['fake-agy'])
    registry.set('antigravity', 'fake-agy', 'low')
    assert '--effort' in AntigravityAdapter().build_command('work', {})
    publisher = Mock()
    monkeypatch.setattr(base, 'default_publisher', publisher)
    backend = Mock()
    backend.execute.return_value = SimpleNamespace(backend='fake', returncode=0, stdout='done', stderr='')
    context = SimpleNamespace(prompt='work', options={'model': 'phase-model', 'effort': 'low'},
        worktree=tmp_path, phase={'name': 'build'}, runner=SimpleNamespace(logger=Mock(), sprint_id='job'),
        backend=backend, timeout_seconds=1, stdout_file=tmp_path/'out', stderr_file=tmp_path/'err')
    adapter.execute(context)
    event = publisher.publish.call_args_list[0].kwargs
    assert event['kind'] == 'agent.started'
    assert event['metadata'] == {'command': 'codex', 'phase': 'build', 'model': 'phase-model', 'effort': 'low', 'source': 'phase'}
    assert registry.describe('codex')['lastUsed'] == {'model': 'phase-model', 'effort': 'low', 'source': 'phase'}
    registry.set('codex', 'gpt-5-codex', 'medium')
    assert registry.describe('codex')['lastUsed']['model'] == 'phase-model'
    argv = backend.execute.call_args.args[0].command
    assert argv[argv.index('--model') + 1] == 'phase-model'


def test_ingress_records_last_used():
    from personas.agent_state_reducer import agent_state_reducer
    agent_state_reducer.apply('gemini', 'agent.started', '', {'model': 'actual', 'effort': 'high', 'source': 'phase'})
    assert agent_models.model_registry.describe('antigravity')['lastUsed']['model'] == 'actual'


def test_concurrent_writes_keep_other_agents():
    from concurrent.futures import ThreadPoolExecutor
    registry = agent_models.model_registry
    other = ModelRegistry(registry.path, registry.codex_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(registry.set, 'claude', 'opus', None),
                   pool.submit(other.set, 'codex', 'gpt-5-codex', 'high')]
        for future in futures:
            future.result()
    assert registry.configured('claude')['default'] == 'opus'
    assert registry.configured('codex')['default'] == 'gpt-5-codex'


def test_phase_setting_is_frozen_during_launch(tmp_path, monkeypatch):
    from agents import base
    from agents.codex import CodexAdapter
    registry = agent_models.model_registry
    registry.set('codex', 'gpt-5-codex', 'low')
    publisher = Mock()
    def update_after_start(**event):
        if event['kind'] == 'agent.started':
            registry.set('codex', 'gpt-5.4', 'high')
    publisher.publish.side_effect = update_after_start
    monkeypatch.setattr(base, 'default_publisher', publisher)
    backend = Mock()
    backend.execute.return_value = SimpleNamespace(backend='fake', returncode=0, stdout='done', stderr='')
    context = SimpleNamespace(prompt='work', options={}, worktree=tmp_path, phase={'name': 'build'},
        runner=SimpleNamespace(logger=Mock(), sprint_id='job'), backend=backend, timeout_seconds=1,
        stdout_file=tmp_path/'out', stderr_file=tmp_path/'err')
    adapter = CodexAdapter()
    adapter.execute(context)
    assert 'gpt-5-codex' in backend.execute.call_args.args[0].command
    assert 'gpt-5.4' in adapter.build_command('next phase', {})
    assert registry.describe('codex')['lastUsed']['model'] == 'gpt-5-codex'
