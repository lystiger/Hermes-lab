import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger("hermes.event_publisher")


def _normalize_id(agent_id: str) -> str:
    if not agent_id:
        return "unknown"
    normalized = str(agent_id).strip().lower()
    if normalized in {"antigravity", "gemini", "agy"}:
        return "gemini"
    return normalized


class RuntimeEventPublisher:
    """
    Runner-side lightweight HTTP publisher that streams sprint execution telemetry
    to the LysStack control-plane API process (POST /internal/events).

    Failure isolation:
    If the control plane URL is not configured or unavailable, execution continues unaffected.
    """

    def __init__(self, control_url: Optional[str] = None, timeout: float = 1.0):
        # Read from constructor or environment variable LYSSTACK_CONTROL_URL
        url = control_url or os.environ.get("LYSSTACK_CONTROL_URL")
        self.control_url = url.rstrip("/") if url else None
        self.timeout = timeout

    def publish(
        self,
        source_id: str,
        kind: str,
        detail: str,
        source_kind: str = "agent",
        source_name: Optional[str] = None,
        duration: Optional[str] = None,
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        accent_color: Optional[str] = None,
    ) -> bool:
        if not self.control_url:
            return False

        normalized_id = _normalize_id(source_id)
        display_name = source_name or normalized_id.capitalize()

        payload = {
            "source": {
                "id": normalized_id,
                "kind": source_kind,
                "displayName": display_name,
                "accentColor": accent_color,
            },
            "kind": kind,
            "detail": detail,
            "duration": duration or "—",
            "jobId": job_id,
            "metadata": metadata or {},
        }

        endpoint = f"{self.control_url}/internal/events"

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status in {200, 201, 202}:
                    return True
                logger.warning(
                    "Control plane returned unexpected status %s for event %s",
                    resp.status,
                    kind,
                )
                return False
        except urllib.error.URLError as err:
            logger.warning(
                "Telemetry event delivery to %s skipped (control API unreachable): %s",
                endpoint,
                err.reason,
            )
            return False
        except Exception as exc:
            logger.warning(
                "Telemetry event delivery failed: %s",
                exc,
            )
            return False


# Singleton runner event publisher configured via environment
default_publisher = RuntimeEventPublisher()
