import sys
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
    assert client.put('/agents/missing/model', json={'model': 'claude-sonnet-5-5'}).status_code == 404
    assert client.put('/agents/claude/model', json={'model': '--evil'}).status_code == 400
    assert client.put('/agents/claude/model', json={'model': 'claude-opus-5-5', 'effort': 'ultra'}).status_code == 400
    assert not registry.path.exists()
    response = client.put('/agents/claude/model', json={'model': 'claude-opus-5-5'})
    assert response.status_code == 200
    assert response.json() == {'default': 'claude-opus-5-5', 'effort': None}
    fresh = ModelRegistry(registry.path, registry.codex_path)
    assert fresh.configured('claude')['default'] == 'claude-opus-5-5'
    models = client.get('/agents/models').json()
    assert models['claude']['configured']['default'] == 'claude-opus-5-5'
    assert models['claude']['lastUsed'] is None
    summaries = {a['id']: a for a in client.get('/agents').json()}
    assert summaries['claude']['model'] == 'claude-opus-5-5'
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


@pytest.mark.skipif(sys.platform == 'win32', reason='fake CLI is a POSIX shell script')
def test_agy_fake_cli_and_cache(tmp_path, monkeypatch):
    cli = tmp_path / 'agy'
    cli.write_text('#!/bin/sh\nprintf "id\\tname\\nmodel-a\\tAlpha\\nmodel-b\\tBeta\\n"\n')
    cli.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path))
    registry = agent_models.model_registry
    assert registry.allowed('gemini') == ['model-a', 'model-b']
    cli.unlink()
    assert registry.allowed('antigravity') == ['model-a', 'model-b']
    registry._cache = (0, [], 60)
    # a failed refresh keeps the last good list
    assert registry.allowed('antigravity') == ['model-a', 'model-b']
    # with no good list yet, the example list is the fallback
    registry._last_good = []
    registry._cache = (0, [], 60)
    assert registry.allowed('antigravity') == ['gemini-2.5-pro', 'gemini-2.5-flash']


def test_atomic_write_failure_preserves_previous(monkeypatch):
    registry = agent_models.model_registry
    registry.set('claude', 'claude-sonnet-5-5', None)
    original = registry.path.read_bytes()
    def fail(*args):
        raise OSError('replace failed')
    monkeypatch.setattr(agent_models.os, 'replace', fail)
    with pytest.raises(OSError, match='replace failed'):
        registry.set('claude', 'claude-opus-5-5', None)
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
    registry.set('claude', 'claude-opus-5-5', None)
    assert 'claude-opus-5-5' in ClaudeAdapter().build_command('work', {})
    registry._cache = (agent_models.time.monotonic(), [{'id': 'fake-agy', 'label': 'Fake', 'efforts': ['low']}], 60)
    registry.set('antigravity', 'fake-agy', 'low')
    assert 'fake-agy-low' in AntigravityAdapter().build_command('work', {})
    assert '--effort' not in AntigravityAdapter().build_command('work', {})
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
        futures = [pool.submit(registry.set, 'claude', 'claude-opus-5-5', None),
                   pool.submit(other.set, 'codex', 'gpt-5-codex', 'high')]
        for future in futures:
            future.result()
    assert registry.configured('claude')['default'] == 'claude-opus-5-5'
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

AGY_SAMPLE = '''gemini-3.8-flash-high\tGemini 3.8 Flash (High)
gemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)
gemini-3.8-flash-low\tGemini 3.8 Flash (Low)
claude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)
claude-opus-4-6-thinking\tClaude Opus 4.6 (Thinking)
gpt-oss-120b-medium\tGPT-OSS 120B (Medium)'''


def test_codex_cache_descriptors_reload_and_fallback(tmp_path, monkeypatch):
    import json
    registry = agent_models.model_registry
    path = tmp_path / 'cache.json'
    monkeypatch.setenv('HERMES_CODEX_MODELS_CACHE', str(path))
    entries = [dict(slug='gpt-6.1-sol', display_name='GPT-6.1-Sol', visibility='list',
                    supported_reasoning_levels=[{'effort': e} for e in ['low', 'max', 'ultra']]),
               dict(slug='hidden', display_name='Hidden', visibility='hide',
                    supported_reasoning_levels=[{'effort': 'high'}])]
    path.write_text(json.dumps({'models': entries}))
    assert registry.models('codex') == [{'id': 'gpt-6.1-sol', 'label': 'GPT-6.1-Sol',
                                        'efforts': ['low', 'max', 'ultra']}]
    registry.codex_path.write_text('model = "hidden"\n')
    assert registry.models('codex')[-1]['efforts'] == ['high']
    registry.codex_path.write_text('model = "uncached"\n')
    assert registry.models('codex')[-1] == {'id': 'uncached', 'label': 'uncached', 'efforts': []}
    entries[0]['supported_reasoning_levels'] = [{'effort': 'medium'}]
    path.write_text(json.dumps({'models': entries}))
    assert registry.models('codex')[0]['efforts'] == ['medium']
    client = TestClient(app)
    assert client.put('/agents/codex/model', json={'model': 'gpt-6.1-sol', 'effort': 'ultra'}).status_code == 400
    assert client.put('/agents/codex/model', json={'model': 'gpt-6.1-sol', 'effort': 'medium'}).status_code == 200
    for content in ['invalid', '{"models": {}}', '{"models": [{"slug": "bad", "supported_reasoning_levels": [null]}]}']:
        path.write_text(content)
        assert registry.models('codex')[0]['efforts'] == ['low', 'medium', 'high']
    path.unlink()
    assert 'gpt-5-codex' in registry.allowed('codex')


def test_agy_descriptors_mapping_and_put(monkeypatch):
    registry = agent_models.model_registry
    run = Mock(return_value=SimpleNamespace(stdout=AGY_SAMPLE))
    monkeypatch.setattr(agent_models.subprocess, 'run', run)
    models = registry.models('agy')
    assert models == [
        {'id': 'gemini-3.8-flash', 'label': 'Gemini 3.8 Flash', 'efforts': ['low', 'medium', 'high']},
        {'id': 'claude-sonnet-4-6', 'label': 'Claude Sonnet 4.6 (Thinking)', 'efforts': []},
        {'id': 'claude-opus-4-6-thinking', 'label': 'Claude Opus 4.6 (Thinking)', 'efforts': []},
        {'id': 'gpt-oss-120b', 'label': 'GPT-OSS 120B', 'efforts': ['medium']}]
    assert run.call_args.kwargs['timeout'] == 20
    assert run.call_args.kwargs['stdin'] == agent_models.subprocess.DEVNULL
    assert registry.agy_cli_model('gemini-3.8-flash') == 'gemini-3.8-flash-medium'
    assert registry.agy_cli_model('gemini-3.8-flash', 'low') == 'gemini-3.8-flash-low'
    assert registry.agy_cli_model('gemini-3.8-flash-high', 'low') == 'gemini-3.8-flash-high'
    assert registry.agy_cli_model('gpt-oss-120b') == 'gpt-oss-120b-medium'
    assert registry.agy_cli_model('claude-sonnet-4-6') == 'claude-sonnet-4-6'
    client = TestClient(app)
    assert client.put('/agents/agy/model', json={'model': 'gpt-oss-120b', 'effort': 'high'}).status_code == 400
    response = client.put('/agents/agy/model', json={'model': 'gemini-3.8-flash-high'})
    assert response.json() == {'default': 'gemini-3.8-flash', 'effort': 'high'}
    result = client.get('/agents/models').json()
    for agent in result.values():
        assert {'configured', 'allowed', 'lastUsed', 'models'} <= agent.keys()
    assert result['gemini']['models'] == models


@pytest.mark.parametrize('agent,stdout,model,effort', [
    ('claude', '{"type":"result","subtype":"success","is_error":false,"result":"done",'
     '"modelUsage":{"claude-small":{"inputTokens":10,"outputTokens":1},'
     '"claude-large":{"inputTokens":2,"outputTokens":20}}}', 'claude-large', None),
    ('codex', 'model: gpt-6.1-sol\nreasoning effort: ultra\ndone', 'gpt-6.1-sol', 'ultra'),
])
def test_reported_model_recording(tmp_path, monkeypatch, agent, stdout, model, effort):
    from agents import base
    from agents.claude import ClaudeAdapter
    from agents.codex import CodexAdapter
    publisher = Mock()
    monkeypatch.setattr(base, 'default_publisher', publisher)
    backend = Mock()
    backend.execute.return_value = SimpleNamespace(backend='fake', returncode=0, stdout=stdout, stderr='')
    context = SimpleNamespace(prompt='work', options={}, worktree=tmp_path, phase={'name': 'build'},
        runner=SimpleNamespace(logger=Mock(), sprint_id='job'), backend=backend, timeout_seconds=1,
        stdout_file=tmp_path/'out', stderr_file=tmp_path/'err')
    adapter = ClaudeAdapter() if agent == 'claude' else CodexAdapter()
    result = adapter.execute(context)
    last = agent_models.model_registry.describe(agent)['lastUsed']
    assert last == dict(model=model, effort=effort, source='reported', requestedModel=None,
                        requestedEffort=None, requestedSource='cli-default')
    assert result.runtime_metadata['reportedModel'] == model
    assert publisher.publish.call_args.kwargs['metadata']['reportedModel'] == model
    if agent == 'claude':
        fresh = ModelRegistry(agent_models.model_registry.path, agent_models.model_registry.codex_path)
        assert model in fresh.allowed('claude')
        assert fresh.models('claude')[-1] == {'id': model, 'label': model, 'efforts': []}
    assert adapter.reported_model(SimpleNamespace(stdout='no model here'), []) == (None, None)


def test_agy_reported_model_and_first_effort(monkeypatch):
    from agents.antigravity import AntigravityAdapter
    registry = agent_models.model_registry
    monkeypatch.setattr(agent_models.subprocess, 'run', Mock(return_value=SimpleNamespace(
        stdout='only-low\tOnly (Low)\n' + AGY_SAMPLE)))
    adapter = AntigravityAdapter()
    assert registry.agy_cli_model('only') == 'only-low'
    command = adapter.build_command('work', {'model': 'gemini-3.8-flash', 'effort': 'high'})
    assert command[command.index('--model') + 1] == 'gemini-3.8-flash-high'
    assert '--effort' not in command
    assert adapter.reported_model(None, command) == ('gemini-3.8-flash', 'high')
    assert adapter.reported_model(None, ['agy']) == (None, None)
    assert adapter.reported_model(None, ['agy', '--model', 'old-high']) == ('old', 'high')


def test_no_report_keeps_cli_default(tmp_path, monkeypatch):
    from agents import base
    from agents.codex import CodexAdapter
    monkeypatch.setattr(base, 'default_publisher', Mock())
    backend = Mock()
    backend.execute.return_value = SimpleNamespace(backend='fake', returncode=0, stdout='done', stderr='')
    context = SimpleNamespace(prompt='work', options={}, worktree=tmp_path, phase={},
        runner=SimpleNamespace(logger=Mock()), backend=backend, timeout_seconds=1,
        stdout_file=tmp_path/'out', stderr_file=tmp_path/'err')
    result = CodexAdapter().execute(context)
    # nothing reported: the backend's runtime metadata passes through untouched
    assert 'reportedModel' not in (getattr(result, 'runtime_metadata', None) or {})
    assert agent_models.model_registry.describe('codex')['lastUsed'] == {
        'model': None, 'effort': None, 'source': 'cli-default'}
