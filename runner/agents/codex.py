import json
import re
from typing import Any, Dict, List, Mapping, Optional

from .base import AgentAdapter
from .errors import SprintRunnerError


class CodexAdapter(AgentAdapter):
    name = "codex"

    def build_command(self, prompt, options, worktree=None):
        command = ["codex", "exec", "--color", "never"]
        if worktree is not None:
            command.extend(["--cd", str(worktree)])
        if options.get("model"):
            command.extend(["--model", str(options["model"])])
        # Worker specs cannot weaken the workspace boundary.
        command.extend(["--sandbox", "workspace-write"])
        if options.get("ephemeral", True):
            command.append("--ephemeral")
        command.append(prompt)
        return command

    def validate_result(self, result, context):
        cleaned = (result.stdout or "").strip()
        if not cleaned:
            raise SprintRunnerError("FAILED_CODEX_EMPTY_OUTPUT", "Codex emitted no output")

        role = ""
        if context and hasattr(context, "phase") and isinstance(context.phase, (dict, Mapping)):
            role = str(context.phase.get("role", "")).lower()

        parsed = self.parse_verification_output(cleaned, result.stderr or "")
        if parsed is None or "verdict" not in parsed:
            if role == "verifier":
                raise SprintRunnerError(
                    "FAILED_CODEX_INVALID_VERDICT",
                    "Codex verifier did not emit a valid verification contract with an explicit verdict",
                )
            return

        try:
            if hasattr(result, "runtime_metadata") and isinstance(result.runtime_metadata, dict):
                result.runtime_metadata.update(parsed)
            else:
                object.__setattr__(result, "runtime_metadata", {**(getattr(result, "runtime_metadata", None) or {}), **parsed})
        except Exception:
            pass

    @classmethod
    def parse_verification_output(cls, stdout_text: str, stderr_text: str = "") -> Optional[Dict[str, Any]]:
        """
        Parses structured verifier contract from Codex output (JSON or structured text blocks).
        Fails closed: returns None if no explicit verdict is provided.
        """
        cleaned = stdout_text.strip()
        if not cleaned:
            return None

        # 1. Try parsing JSON (direct or inside markdown fences)
        json_obj = None
        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                json_obj = json.loads(cleaned)
            except Exception:
                pass

        if json_obj is None:
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if json_match:
                try:
                    json_obj = json.loads(json_match.group(1))
                except Exception:
                    pass

        if isinstance(json_obj, dict):
            raw_verdict = str(json_obj.get("verdict") or json_obj.get("status") or "").lower().strip()
            summary = str(json_obj.get("summary") or json_obj.get("message") or "")
            findings = list(json_obj.get("findings") or [])

            # Fail closed: verdict MUST be explicitly passed/success or failed/fail/error
            if raw_verdict in ("passed", "pass", "success", "ok"):
                is_pass = True
                norm_verdict = "passed"
                repairable = bool(json_obj.get("repairable", False))
            elif raw_verdict in ("failed", "fail", "error"):
                is_pass = False
                norm_verdict = "failed"
                repairable = bool(json_obj.get("repairable", True))
            else:
                # Do NOT fabricate or infer verdict from generic flags like {"success": true} or {"summary": "looks fine"}
                return None

            obs_list = []
            if is_pass:
                obs_list.append({
                    "kind": "verification_success",
                    "content": f"Codex verification passed: {summary or 'all verification checks passed.'}",
                    "metadata": {"verdict": "passed", "findings": findings},
                })
            else:
                obs_list.append({
                    "kind": "verification_failure",
                    "content": f"Codex verification failed: {summary or 'defects detected.'}. Findings: {'; '.join(str(f) for f in findings) if findings else 'unspecified'}",
                    "metadata": {
                        "verdict": "failed",
                        "repairable": repairable,
                        "findings": findings,
                        "requires_follow_up": True,
                    },
                })

            return {
                "verdict": norm_verdict,
                "summary": summary,
                "repairable": repairable,
                "findings": findings,
                "structured_verdict": json_obj,
                "trigger_replan": not is_pass,
                "replan_reason": f"Codex verification failure: {summary}" if not is_pass else None,
                "observations": obs_list,
            }

        # 2. Try parsing structured text format (e.g. VERDICT: PASS / FAIL)
        verdict_match = re.search(r"VERDICT\s*:\s*(PASS|FAIL|PASSED|FAILED|SUCCESS|ERROR)\b", cleaned, re.IGNORECASE)
        if verdict_match:
            v_str = verdict_match.group(1).upper()
            is_pass = v_str in ("PASS", "PASSED", "SUCCESS")
            norm_verdict = "passed" if is_pass else "failed"

            summary_match = re.search(r"SUMMARY\s*:\s*([^\n]+)", cleaned, re.IGNORECASE)
            summary = summary_match.group(1).strip() if summary_match else ""

            repairable_match = re.search(r"REPAIRABLE\s*:\s*(TRUE|FALSE)\b", cleaned, re.IGNORECASE)
            repairable = (repairable_match.group(1).upper() == "TRUE") if repairable_match else (not is_pass)

            findings = []
            findings_match = re.search(r"FINDINGS\s*:\s*(.*?)(?=\n[A-Z_]+\s*:|\Z)", cleaned, re.DOTALL | re.IGNORECASE)
            if findings_match:
                for line in findings_match.group(1).strip().splitlines():
                    cleaned_line = line.strip().lstrip("-*• ").strip()
                    if cleaned_line:
                        findings.append(cleaned_line)

            obs_list = []
            if is_pass:
                obs_list.append({
                    "kind": "verification_success",
                    "content": f"Codex verification passed: {summary or 'all verification checks passed.'}",
                    "metadata": {"verdict": "passed", "findings": findings},
                })
            else:
                obs_list.append({
                    "kind": "verification_failure",
                    "content": f"Codex verification failed: {summary or 'defects detected.'}. Findings: {'; '.join(findings) if findings else 'unspecified'}",
                    "metadata": {
                        "verdict": "failed",
                        "repairable": repairable,
                        "findings": findings,
                        "requires_follow_up": True,
                    },
                })

            return {
                "verdict": norm_verdict,
                "summary": summary,
                "repairable": repairable,
                "findings": findings,
                "structured_verdict": {
                    "verdict": norm_verdict,
                    "summary": summary,
                    "repairable": repairable,
                    "findings": findings,
                },
                "trigger_replan": not is_pass,
                "replan_reason": f"Codex verification failure: {summary}" if not is_pass else None,
                "observations": obs_list,
            }

        return None
