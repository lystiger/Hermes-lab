"""Denial detection reads real denial messages, not file content echoed into stderr."""
from runner.agents.denials import denial_lines


def test_real_denial_line_is_reported():
    stderr = "error: permission denied: git commit -m 'x'\n"

    assert denial_lines(stderr) == ["error: permission denied: git commit -m 'x'"]


def test_diff_lines_that_quote_the_phrase_are_not_denials():
    stderr = "\n".join([
        '+        "permission denied",',
        '-    if "permission denied" in line.lower()]',
        ' context: "permission denied" in a fixture',
        "\tindented: permission denied text",
        "@@ runner/agents/codex.py @@ permission denied",
    ])

    assert denial_lines(stderr) == []


def test_empty_stderr_has_no_denials():
    assert denial_lines(None) == []
    assert denial_lines("") == []
