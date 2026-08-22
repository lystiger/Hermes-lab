import json
import logging
import os
import sys
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Union

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from normalization import normalize_agent_id

logger = logging.getLogger("hermes.event_publisher")


class RuntimeEventPublisher:
    """
    Runner-side lightweight HTTP publisher that streams sprint execution telemetry,
    messages, threads, and artifacts to the LysStack control-plane API process.

    Failure isolation:
    If the control plane URL is not configured or unavailable, execution continues unaffected.
    """

    def __init__(self, control_url: Optional[str] = None, timeout: float = 1.0):
        url = control_url or os.environ.get("LYSSTACK_CONTROL_URL")
        self.control_url = url.rstrip("/") if url else None
        self.timeout = timeout

    def _post_json(self, endpoint_path: str, payload: Dict[str, Any]) -> bool:
        if not self.control_url:
            return False

        endpoint = f"{self.control_url}{endpoint_path}"
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
                    "Control plane returned unexpected status %s for %s",
                    resp.status,
                    endpoint_path,
                )
                return False
        except urllib.error.URLError as err:
            logger.warning(
                "Telemetry delivery to %s skipped (control API unreachable): %s",
                endpoint,
                err.reason,
            )
            return False
        except Exception as exc:
            logger.warning("Telemetry delivery failed: %s", exc)
            return False

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
        normalized_id = normalize_agent_id(source_id) if source_kind == "agent" else source_id
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
        return self._post_json("/internal/events", payload)

    def publish_thread(
        self,
        thread_id: str,
        job_id: Optional[str] = None,
        title: Optional[str] = None,
        participants: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        payload = {
            "id": thread_id,
            "jobId": job_id,
            "title": title or f"Thread {thread_id}",
            "participants": participants or [],
        }
        return self._post_json("/internal/threads", payload)

    def publish_message(
        self,
        thread_id: str,
        from_actor: Dict[str, Any],
        to_actors: List[Dict[str, Any]],
        kind: str,
        text: str,
        intent: Optional[str] = None,
        job_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        artifact_refs: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        payload = {
            "threadId": thread_id,
            "from": from_actor,
            "to": to_actors,
            "kind": kind,
            "text": text,
            "intent": intent,
            "jobId": job_id,
            "phaseId": phase_id,
            "artifactRefs": artifact_refs or [],
            "metadata": metadata or {},
        }
        return self._post_json("/internal/messages", payload)

    def publish_artifact(
        self,
        artifact: Dict[str, Any],
    ) -> bool:
        return self._post_json("/internal/artifacts", artifact)


default_publisher = RuntimeEventPublisher()
