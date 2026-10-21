import shutil

import pytest

from security import scan


def _write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_clean_repo_passes_the_secret_check(tmp_path):
    _write(tmp_path, "app.py", "x = 1\n")

    assert scan.scan_secrets(tmp_path) == {"check": "secrets", "status": "PASS", "findings": []}


def test_secret_shapes_are_found_and_masked(tmp_path):
    # Built at run time, so no credential-shaped string sits in the repository itself.
    fake_aws = "AKIA" + "X" * 16
    fake_key = "-----BEGIN " + "RSA PRIVATE KEY-----"
    _write(tmp_path, "config/settings.py", f'AWS = "{fake_aws}"\napi_token = "abcdefghijklmnop"\n')  # secret-scan: fixture
    _write(tmp_path, "keys/id.pem", fake_key + "\n")

    result = scan.scan_secrets(tmp_path)

    assert result["status"] == "FAIL"
    rules = {f["rule"] for f in result["findings"]}
    assert {"aws-access-key", "assigned-secret", "private-key"} <= rules
    assert all(fake_aws not in f["evidence"] for f in result["findings"])


def test_secret_scan_skips_virtualenvs_and_git(tmp_path):
    _write(tmp_path, ".venv/lib/leak.py", 'token = "abcdefghijklmnop"\n')  # secret-scan: fixture
    _write(tmp_path, ".git/config", 'token = "abcdefghijklmnop"\n')  # secret-scan: fixture

    assert scan.scan_secrets(tmp_path)["status"] == "PASS"


@pytest.mark.skipif(not scan._module_present("bandit"), reason="bandit not installed")
def test_python_injection_pattern_fails_the_static_check(tmp_path):
    _write(tmp_path, "app.py", 'import subprocess\nsubprocess.call("ls " + input(), shell=True)\n')

    result = scan.scan_python(tmp_path)

    assert result["status"] == "FAIL"
    assert any(f["rule"] == "B602" for f in result["findings"])


def test_a_missing_scanner_is_unproven_not_a_pass(tmp_path, monkeypatch):
    _write(tmp_path, "app.py", "x = 1\n")
    monkeypatch.setattr(scan, "_module_present", lambda name: False)
    monkeypatch.setattr(scan.shutil, "which", lambda name: None)

    assert scan.scan_python(tmp_path)["status"] == "UNPROVEN"
    assert scan.scan_dependencies(tmp_path)["status"] == "UNPROVEN"


def test_dependencies_without_a_requirements_file_are_unproven(tmp_path):
    assert scan.scan_dependencies(tmp_path) == {"check": "dependencies", "status": "UNPROVEN",
                                                "reason": "no requirements.txt", "findings": []}


def test_advisories_from_pip_audit_become_findings(tmp_path, monkeypatch):
    _write(tmp_path, "requirements.txt", "somepkg==1.0\n")
    monkeypatch.setattr(scan, "_module_present", lambda name: True)
    fake = {"dependencies": [{"name": "somepkg", "version": "1.0",
                              "vulns": [{"id": "PYSEC-0001", "fix_versions": ["1.0.1"]}]}]}
    monkeypatch.setattr(scan, "_run_json", lambda argv, cwd: (fake, ""))

    result = scan.scan_dependencies(tmp_path)

    assert result["status"] == "FAIL"
    assert result["findings"][0]["rule"] == "PYSEC-0001"


def test_the_verdict_is_fail_if_any_check_fails_and_unproven_otherwise(tmp_path, monkeypatch):
    _write(tmp_path, "app.py", 'token = "abcdefghijklmnop"\n')  # secret-scan: fixture
    monkeypatch.setattr(scan, "scan_python", lambda root: {"check": "python-static", "status": "PASS", "findings": []})
    monkeypatch.setattr(scan, "scan_dependencies", lambda root: {"check": "dependencies", "status": "UNPROVEN",
                                                                 "reason": "x", "findings": []})

    assert scan.report(tmp_path)["verdict"] == "FAIL"

    (tmp_path / "app.py").write_text("x = 1\n")
    assert scan.report(tmp_path)["verdict"] == "UNPROVEN"


def test_low_severity_findings_are_notes_not_failures(tmp_path, monkeypatch):
    _write(tmp_path, "app.py", "x = 1\n")
    monkeypatch.setattr(scan, "_module_present", lambda name: True)
    fake = {"results": [{"test_id": "B101", "filename": "./app.py", "line_number": 1,
                         "issue_severity": "LOW", "issue_text": "assert used"}]}
    monkeypatch.setattr(scan, "_run_json", lambda argv, cwd: (fake, ""))

    result = scan.scan_python(tmp_path)

    assert result["status"] == "PASS" and result["findings"] == [] and len(result["notes"]) == 1
