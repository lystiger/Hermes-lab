from personas.persona import DEFAULT_PERSONAS


def test_codex_edit_restriction_names_the_verifier_role():
    persona = DEFAULT_PERSONAS["codex"]
    for role in ("builder", "verifier"):
        text = persona.render_prompt_section("codex", role)
        assert "When your role is verifier, never modify source files" in text
        assert "Never modify source files in verifier role" not in text
        assert f"Role: {role}" in text
