# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""End-to-end test asserting a unified trace lands in Phoenix.

Skipped unless both `GATEWAY_IP` and `PHOENIX_BASE_URL` are set. With them
set, the test drives one A2A `message/send` against the deployed
time-agent (a question that forces a `get_current_time` tool call), then
polls Phoenix's spans API for both projects until it finds a `trace_id`
that appears in both `time-agent` and `time-mcp-server`. Fails after
60 seconds with a clear error.

Run from `lab-5/time-agent/`:

    GATEWAY_IP=<svc-ip> \\
    PHOENIX_BASE_URL=http://<svc-ip>/phoenix \\
    uv run pytest tests/integration/test_phoenix_trace.py -q
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

GATEWAY_IP = os.environ.get("GATEWAY_IP")
PHOENIX_BASE_URL = os.environ.get("PHOENIX_BASE_URL")
TIMEOUT_SECONDS = 60
POLL_INTERVAL = 2.0

pytestmark = pytest.mark.skipif(
    not (GATEWAY_IP and PHOENIX_BASE_URL),
    reason="Set GATEWAY_IP and PHOENIX_BASE_URL to run the Phoenix trace e2e test",
)


def _agent_url() -> str:
    # kagent exposes BYO agents at /api/a2a/<namespace>/<agent>/ via the
    # gateway. The trailing slash is required by the A2A SDK.
    return f"http://{GATEWAY_IP}/api/a2a/kagent/time-agent/"


def _send_question(question: str) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": str(uuid.uuid4()),
                "parts": [{"kind": "text", "text": question}],
            }
        },
    }
    response = requests.post(_agent_url(), json=payload, timeout=30)
    response.raise_for_status()


def _spans_for(project: str) -> list[dict]:
    url = f"{PHOENIX_BASE_URL.rstrip('/')}/v1/projects/{project}/spans"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    body = response.json()
    # Phoenix returns either {"data": [...]} or a raw list depending on
    # version. Accept both rather than pinning to one shape.
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    if isinstance(body, list):
        return body
    return []


def _trace_ids(spans: list[dict]) -> set[str]:
    ids: set[str] = set()
    for span in spans:
        ctx = span.get("context") or {}
        trace_id = ctx.get("trace_id") or span.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            ids.add(trace_id)
    return ids


def test_unified_trace_across_agent_and_mcp_server() -> None:
    _send_question("What time is it in UTC right now?")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            agent_traces = _trace_ids(_spans_for("time-agent"))
            mcp_traces = _trace_ids(_spans_for("time-mcp-server"))
            shared = agent_traces & mcp_traces
            if shared:
                return
        except Exception as exc:  # noqa: BLE001 — polling diagnostics
            last_error = exc
        time.sleep(POLL_INTERVAL)

    pytest.fail(
        "No shared trace_id between time-agent and time-mcp-server within "
        f"{TIMEOUT_SECONDS}s. Last polling error: {last_error!r}"
    )
