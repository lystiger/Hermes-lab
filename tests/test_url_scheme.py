import urllib.request

import pytest

from security import urls
from security.urls import checked_urlopen


@pytest.mark.parametrize("target", ["file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/"])
def test_other_schemes_are_refused_before_any_request(monkeypatch, target):
    def boom(*args, **kwargs):
        raise AssertionError("urlopen must not be reached")

    monkeypatch.setattr(urls.urllib.request, "urlopen", boom)

    with pytest.raises(ValueError, match="refusing"):
        checked_urlopen(target, timeout=1)
    with pytest.raises(ValueError, match="refusing"):
        checked_urlopen(urllib.request.Request(target), timeout=1)


def test_http_and_https_are_opened(monkeypatch):
    opened = []
    monkeypatch.setattr(urls.urllib.request, "urlopen", lambda target, timeout: opened.append(target) or "ok")

    assert checked_urlopen("http://127.0.0.1:8000/health", timeout=1) == "ok"
    assert checked_urlopen(urllib.request.Request("https://example.com/x"), timeout=1) == "ok"
    assert len(opened) == 2


def test_the_runner_still_imports_when_run_from_its_own_folder(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path[0]=sys.argv[1]; import importlib; "
         "import runner.control_plane.event_publisher as m; print('ok')", str(repo / "runner")],
        cwd=str(repo / "runner"), capture_output=True, text=True, check=False,
        env={"PYTHONPATH": str(repo), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
