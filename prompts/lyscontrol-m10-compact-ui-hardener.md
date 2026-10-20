# LysControl M10 hardener

Review the builder's compact-UI change (see the builder prompt). Look for concrete defects only: text that still overlaps or clips without a tooltip, a truncated value with no `title`, a fixture that is too short to test anything, a test that passes for the wrong reason, lost information (a value removed rather than shortened), and anything that breaks at 900 px.
Fix only concrete defects, with a test for each. Do not restyle. Run the four gates. Write HANDOFF_HARDENER.md listing each defect and fix (or "none"). Commit with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>` only if you changed files.
