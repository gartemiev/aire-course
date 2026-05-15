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

"""Integration test: runs the real agent against the real MCP server and LLM.

Skipped unless TIME_MCP_URL is reachable (port-forward the gateway first).
"""

import os

import pytest
import requests
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


def _mcp_reachable() -> bool:
    """Send a JSON-RPC initialize to TIME_MCP_URL and accept only an MCP response."""
    url = os.getenv("TIME_MCP_URL", "http://localhost:8080/mcp")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest-probe", "version": "0"},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=2)
    except requests.RequestException:
        return False
    if resp.status_code >= 400:
        return False
    return '"result"' in resp.text or '"error"' in resp.text


pytestmark = pytest.mark.skipif(
    not _mcp_reachable(),
    reason="MCP gateway not reachable; port-forward agentgateway-external first",
)


def _collect(prompt: str) -> list:
    from app.agent import root_agent

    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    return list(
        runner.run(
            new_message=message,
            user_id="test",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )


def _tool_calls(events) -> list[str]:
    names: list[str] = []
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            call = getattr(part, "function_call", None)
            if call and call.name:
                names.append(call.name)
    return names


def _text(events) -> str:
    chunks = []
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.text:
                chunks.append(part.text)
    return "".join(chunks)


def test_current_time_calls_mcp_tool() -> None:
    events = _collect("What time is it right now?")
    assert "get_current_time" in _tool_calls(events), (
        f"expected get_current_time call, got {_tool_calls(events)}"
    )
    assert _text(events).strip(), "expected a final text answer"


def test_convert_time_calls_mcp_tool() -> None:
    events = _collect(
        "Convert 2026-05-15T10:00:00 from UTC to America/New_York."
    )
    assert "convert_time" in _tool_calls(events), (
        f"expected convert_time call, got {_tool_calls(events)}"
    )
