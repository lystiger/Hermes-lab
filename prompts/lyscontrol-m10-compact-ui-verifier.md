# LysControl M10 verifier

Do not change product source. Independently check the compact-UI change on this branch:
1. Diff against the base. Confirm long values are truncated with a `title` or wrapped, not dropped, and that the Overview has fewer words than before.
2. Start the dev server in mock mode yourself and run `node scripts/ui-check.mjs` on it. Report the issue count per width, and open the 1280 and 900 px screenshots and say what you see.
3. Run the four gates and report exit codes.
Write HANDOFF_CODEX.md with PASS or FAIL, the evidence (commands, exit codes, counts), and any concern. No commits.
