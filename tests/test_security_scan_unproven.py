"""Bug 9 test.

Bug 9: fixed (test_bandit_error_or_pip_audit_skip_reports_unproven) - reproduced and fixed.
Not marked not reproduced.
"""

from security import scan


def test_bandit_error_or_pip_audit_skip_reports_unproven(tmp_path, monkeypatch):
    """
    A Bandit run that reports errors (a file it could not analyse) and a dependency that pip-audit
    skipped (no advisory lookup done) are both gaps in coverage, so the verdict must be UNPROVEN.
    Current code reads only "results" and "vulns": security/scan.py line 94 turns an empty
    blocking list into PASS, and line 110 turns a skipped dependency (no "vulns") into no findings.
    No real findings exist here, so FAIL is not expected.
    """
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("internal-pkg==1.0\n", encoding="utf-8")

    monkeypatch.setattr(scan, "_module_present", lambda name: True)

    def fake_run_json(argv, cwd):
        if "bandit" in argv:
            return {"errors": [{"filename": "./app.py", "reason": "could not parse file"}], "results": []}, ""
        if "pip_audit" in argv:
            return {"dependencies": [{"name": "internal-pkg", "version": "1.0", "vulns": [],
                                      "skip_reason": "could not be audited"}]}, ""
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(scan, "_run_json", fake_run_json)

    result = scan.report(tmp_path)

    assert result["verdict"] == "UNPROVEN", f"expected UNPROVEN, got {result['verdict']}: {result['checks']}"
    assert result["verdict"] != "PASS"
