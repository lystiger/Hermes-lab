import json
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from agents.claude import ClaudeAdapter
from agents.antigravity import AntigravityAdapter
from agents.errors import SprintRunnerError
from runner.backends.base import ExecutionRequest
from runner.backends.execution_registry import default_execution_registry
from runner.backends.subprocess_backend import SubprocessBackend


@pytest.mark.parametrize('ignore_term', [False, True])
def test_cancel_real_process_group(tmp_path, ignore_term):
    pidfile = tmp_path / 'pid'
    script = ('import os,signal,time; '
              + ('signal.signal(signal.SIGTERM, signal.SIG_IGN); ' if ignore_term else '')
              + f'open({str(pidfile)!r}, "w").write(str(os.getpid())); time.sleep(60)')
    seen = []
    backend = SubprocessBackend(sprint_id='m8-job', cancel_grace_seconds=.15, event_sink=seen.append)
    request = ExecutionRequest('fake', [sys.executable, '-c', script], tmp_path, 10,
                               tmp_path/'out', tmp_path/'err')
    with ThreadPoolExecutor() as pool:
        future = pool.submit(backend.execute, request)
        deadline = time.monotonic() + 5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert pidfile.exists()
        pid = int(pidfile.read_text())
        start = time.monotonic()
        default_execution_registry.cancel_job('m8-job')
        with pytest.raises(SprintRunnerError) as exc:
            future.result(timeout=2)
        assert exc.value.code == 'FAILED_CANCELLED'
        assert time.monotonic() - start < 1
        with pytest.raises(ProcessLookupError):
            os.killpg(pid, 0)
    assert [e.kind for e in seen][-2:] == ['execution.cancelled', 'execution.resource_released']
    assert not default_execution_registry.cancel_execution(seen[0].metadata['executionId'])


def test_real_normal_and_timeout(tmp_path):
    backend = SubprocessBackend(cancel_grace_seconds=.05)
    def req(script, timeout=2):
        return ExecutionRequest('fake', [sys.executable, '-c', script], tmp_path, timeout,
                                tmp_path/'out', tmp_path/'err')
    result = backend.execute(req('import sys; print("hello"); print("err", file=sys.stderr)'))
    assert (result.returncode, result.stdout, result.stderr) == (0, 'hello\n', 'err\n')
    with pytest.raises(SprintRunnerError) as exc:
        backend.execute(req('import time; print("partial", flush=True); time.sleep(60)', .15))
    assert exc.value.code == 'FAILED_TIMEOUT'
    assert (tmp_path/'out').read_text() == 'partial\n'


@pytest.mark.parametrize('adapter', ['claude', 'agy'])
@pytest.mark.parametrize('case', ['recover', 'empty', 'git', 'ceiling', 'strict', 'scope'])
def test_denial_policy(adapter, case):
    denial = 'python -c pass'
    if case == 'git':
        denial = 'git -C /tmp commit -m bad'
    if case == 'scope':
        denial = 'write outside worktree /etc/example'
    denials = [denial] * (21 if case == 'ceiling' else 1)
    options = {'fail_on_permission_denial': case == 'strict'}
    metadata = {}
    if adapter == 'claude':
        data = {'type':'result', 'subtype':'success', 'is_error':False,
                'result': '' if case == 'empty' else 'done',
                'permission_denials':[{'tool_input':{'command':d}} for d in denials]}
        call = lambda: ClaudeAdapter.parse_json(json.dumps(data), options=options, metadata=metadata)
    else:
        stream = [json.dumps({'event':'tool', 'error':'permission denied', 'command':d}) for d in denials]
        if case != 'empty':
            stream.append(json.dumps({'event':'result', 'result':{'status':'SUCCESS', 'summary':'done'}}))
        call = lambda: AntigravityAdapter.parse_stream_json('\n'.join(stream), options=options, metadata=metadata)
    if case == 'recover':
        call()
    else:
        with pytest.raises(SprintRunnerError) as exc:
            call()
        assert exc.value.code == 'FAILED_PERMISSION_DENIED'
    assert metadata['permission_denial_count'] == len(denials)
    assert len(metadata['observations']) == len(denials)
    assert all(len(o['content']) <= 300 for o in metadata['observations'])


@pytest.mark.parametrize('case', ['recover', 'empty', 'git', 'ceiling', 'strict'])
def test_codex_denial_policy(tmp_path, case):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from agents.base import AgentContext
    from agents.codex import CodexAdapter
    from runner.backends.base import ExecutionResult
    denial = 'permission denied: ' + ('git commit -m bad' if case == 'git' else 'python -c pass')
    result = ExecutionResult(('codex',), 0, '' if case == 'empty' else 'done',
                             '\n'.join([denial] * (21 if case == 'ceiling' else 1)), 'fake', {})
    context = AgentContext(SimpleNamespace(logger=MagicMock()), {}, tmp_path, 'prompt',
                           {'fail_on_permission_denial':case == 'strict'}, tmp_path/'out', tmp_path/'err',
                           5, SimpleNamespace(execute=lambda request:result))
    if case == 'recover':
        assert CodexAdapter().execute(context) is result
    else:
        with pytest.raises(SprintRunnerError) as exc:
            CodexAdapter().execute(context)
        assert exc.value.code == 'FAILED_PERMISSION_DENIED'


@pytest.mark.parametrize('adapter', ['claude', 'agy'])
def test_structured_write_denial_outside_worktree(tmp_path, adapter):
    denial = {'tool_name':'Write', 'tool_input':{'file_path':'../outside.txt'}}
    if adapter == 'claude':
        text = json.dumps({'type':'result','subtype':'success','is_error':False,
                           'result':'done', 'permission_denials':[denial]})
        call = lambda: ClaudeAdapter.parse_json(text, worktree=tmp_path)
    else:
        denial.update(event='tool', error='permission denied')
        text = json.dumps(denial) + '\n' + json.dumps({'event':'result','result':{'status':'SUCCESS'}})
        call = lambda: AntigravityAdapter.parse_stream_json(text, worktree=tmp_path)
    with pytest.raises(SprintRunnerError) as exc:
        call()
    assert exc.value.code == 'FAILED_PERMISSION_DENIED'


def test_denial_command_truncation():
    metadata = {}
    command = 'python ' + 'a'*500
    ClaudeAdapter.parse_json(json.dumps({'type':'result','subtype':'success','is_error':False,
                                       'result':'done', 'permission_denials':[{'tool_input':{'command':command}}]}),
                             metadata=metadata)
    assert metadata['observations'][0]['metadata']['command'] == command[:300]


def test_registry_job_cancel_is_scoped_and_finished_is_noop():
    from runner.backends.execution_registry import ExecutionRegistry
    registry = ExecutionRegistry()
    a, b = threading.Event(), threading.Event()
    registry.register_execution('a', 'job-a', object(), a.set)
    registry.register_execution('b', 'job-b', object(), b.set)
    registry.cancel_job('job-a')
    assert a.is_set() and not b.is_set()
    registry.unregister_execution('b')
    assert not registry.cancel_execution('b')


def test_cancel_reaches_descendant_group(tmp_path):
    pidfile = tmp_path/'child'
    child_code = f'import os,time; open({str(pidfile)!r}, "w").write(str(os.getpid())); time.sleep(60)'
    script = ('import subprocess,sys,time; '
              f'p=subprocess.Popen([sys.executable,"-c",{child_code!r}]); '
              'time.sleep(60)')
    backend = SubprocessBackend(sprint_id='descendants', cancel_grace_seconds=.1)
    request = ExecutionRequest('fake', [sys.executable,'-c',script], tmp_path, 10,
                               tmp_path/'out', tmp_path/'err')
    with ThreadPoolExecutor() as pool:
        future = pool.submit(backend.execute, request)
        deadline = time.monotonic()+5
        while not pidfile.exists() and time.monotonic()<deadline:
            time.sleep(.01)
        assert pidfile.exists()
        pid = int(pidfile.read_text())
        default_execution_registry.cancel_job('descendants')
        with pytest.raises(SprintRunnerError):
            future.result(timeout=2)
        # Orphan zombies may await PID 1 reaping; they cannot execute or spend quota.
        stat = __import__('pathlib').Path(f'/proc/{pid}/stat')
        assert not stat.exists() or stat.read_text().split(') ')[1].startswith('Z')


@pytest.mark.parametrize('adapter', ['claude', 'agy'])
def test_phase_policy_and_custom_ceiling(adapter):
    if adapter == 'claude':
        text = json.dumps({'type':'result', 'subtype':'success', 'is_error':False,
                           'result':'done', 'permission_denials':['python -c pass']})
        parse = ClaudeAdapter.parse_json
    else:
        text = json.dumps({'event':'tool','error':'permission denied','command':'python -c pass'})+'\n'+json.dumps({'event':'result','result':{'status':'SUCCESS'}})
        parse = AntigravityAdapter.parse_stream_json
    for phase in ({'fail_on_permission_denial':True}, {'permission_denial_ceiling':0}):
        with pytest.raises(SprintRunnerError) as exc:
            parse(text, phase=phase)
        assert exc.value.code == 'FAILED_PERMISSION_DENIED'


@pytest.mark.parametrize('command, fatal', [('git -C /tmp branch -D branch',True),
                                           ('git -c key=value remote set-url origin URL',True),
                                           ('git status',False), ('git branch --show-current',False),
                                           ('git log --grep commit',False)])
def test_git_denial_classification(command, fatal):
    text = json.dumps({'type':'result','subtype':'success','is_error':False,
                       'result':'recovered','permission_denials':[{'tool_input':{'command':command}}]})
    if fatal:
        with pytest.raises(SprintRunnerError) as exc:
            ClaudeAdapter.parse_json(text)
        assert exc.value.code == 'FAILED_PERMISSION_DENIED'
    else:
        ClaudeAdapter.parse_json(text)


def test_codex_verifier_keeps_denial_observation(tmp_path):
    from types import SimpleNamespace
    from agents.codex import CodexAdapter
    from runner.backends.base import ExecutionResult
    result = ExecutionResult(('codex',),0,'VERDICT: PASS\nSUMMARY: done',
                             'permission denied: python -c pass', 'fake', {})
    CodexAdapter().validate_result(result, SimpleNamespace(phase={'role':'verifier'}, options={},worktree=tmp_path))
    assert {o['kind'] for o in result.runtime_metadata['observations']} == {'permission_denial','verification_success'}


def test_herdr_registry_cancel_interrupts_owned_pane(tmp_path, monkeypatch):
    from runner.backends.herdr_backend import HerdrBackend
    from runner.backends.base import ExecutionResult
    seen, interrupted, entered = [], threading.Event(), threading.Event()
    backend = HerdrBackend(tmp_path, 'herdr-cancel', event_sink=seen.append)
    monkeypatch.setattr(backend, 'preflight', lambda command:None)
    monkeypatch.setattr(backend, '_ensure_workspace', lambda cwd:None)
    monkeypatch.setattr(backend, '_create_worker_pane', lambda request:'owned-pane')
    monkeypatch.setattr(backend, '_interrupt_pane', lambda pane:interrupted.set())
    def run(request, trace, pane):
        entered.set()
        assert interrupted.wait(2)
        return ExecutionResult((), 130, '', '', 'herdr')
    monkeypatch.setattr(backend, '_run_in_pane', run)
    request = ExecutionRequest('fake', ['fake'],tmp_path,5,tmp_path/'out',tmp_path/'err')
    with ThreadPoolExecutor() as pool:
        future = pool.submit(backend.execute, request)
        assert entered.wait(2)
        default_execution_registry.cancel_job('herdr-cancel')
        with pytest.raises(SprintRunnerError) as exc:
            future.result(timeout=2)
        assert exc.value.code == 'FAILED_CANCELLED'
    assert [e.kind for e in seen][-2:] == ['execution.cancelled','execution.resource_released']


def test_openrig_registry_cancel_sets_backend_event(tmp_path, monkeypatch):
    from runner.backends.openrig_backend import OpenRigBackend
    entered = threading.Event()
    backend = OpenRigBackend(tmp_path, 'openrig-cancel')
    def run(request, trace):
        entered.set()
        assert backend._cancel_event.wait(2)
        backend._check_cancelled('test')
    monkeypatch.setattr(backend, '_execute', run)
    request = ExecutionRequest('fake',['fake'],tmp_path,5,tmp_path/'out',tmp_path/'err')
    with ThreadPoolExecutor() as pool:
        future = pool.submit(backend.execute, request)
        assert entered.wait(2)
        default_execution_registry.cancel_job('openrig-cancel')
        with pytest.raises(SprintRunnerError) as exc:
            future.result(timeout=2)
        assert exc.value.code == 'FAILED_OPENRIG_CANCELLED'


def test_literal_shell_write_outside_worktree_is_fatal(tmp_path):
    text = json.dumps({'type':'result','subtype':'success','is_error':False,'result':'recovered',
                       'permission_denials':[{'tool_name':'Bash','tool_input':{'command':'touch /etc/hosts'}}]})
    with pytest.raises(SprintRunnerError) as exc:
        ClaudeAdapter.parse_json(text, worktree=tmp_path)
    assert exc.value.code == 'FAILED_PERMISSION_DENIED'
