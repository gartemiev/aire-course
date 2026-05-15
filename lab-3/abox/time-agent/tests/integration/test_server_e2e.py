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

"""A2A smoke test for kagent BYO entrypoint.

Boots app.a2a_app:a2a_app on a random port and asserts the well-known agent
card is served with streaming enabled and both MCP tools listed as skills.

Skipped unless TIME_MCP_URL is reachable, because a2a_app builds the agent
card at startup via AgentCardBuilder — which enumerates MCP tools — so the
subprocess can't start without a live MCP server. This is a feature, not a
bug: the BYO container should fail loud if MCP is missing.
"""

import logging
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import pytest
import requests
from requests.exceptions import RequestException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _mcp_reachable() -> bool:
    """Verify there's an actual MCP server at TIME_MCP_URL (not just any HTTP).

    Sends a JSON-RPC `initialize` and accepts the response if it parses and
    contains either a `result` or an `error` field — both prove the server
    speaks JSON-RPC. A bare 200 from some other service won't fool us.
    """
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
    except RequestException:
        return False
    if resp.status_code >= 400:
        return False
    body = resp.text
    return '"result"' in body or '"error"' in body


pytestmark = pytest.mark.skipif(
    not _mcp_reachable(),
    reason="TIME_MCP_URL not reachable; a2a_app needs MCP at startup to build the agent card",
)


def _wait(url: str, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=2).status_code < 500:
                return True
        except RequestException:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def a2a_server() -> Iterator[str]:
    port = _free_port()
    env = os.environ.copy()
    env.setdefault("MODEL_PROVIDER", "openai")
    # OPENAI_API_BASE can stay harmless — the LLM is never called in this
    # test; we only hit the agent card endpoint.
    env.setdefault("OPENAI_API_BASE", f"http://127.0.0.1:{_free_port()}/v1")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.a2a_app:a2a_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def _log(pipe: Any) -> None:
        for line in iter(pipe.readline, ""):
            logger.info(line.rstrip())

    threading.Thread(target=_log, args=(proc.stdout,), daemon=True).start()

    base = f"http://127.0.0.1:{port}"
    if not _wait(f"{base}/.well-known/agent-card.json"):
        proc.terminate()
        proc.wait()
        pytest.fail("A2A server did not start in time")

    yield base
    proc.terminate()
    proc.wait()


def test_agent_card_served(a2a_server: str) -> None:
    """BYO entrypoint serves a well-known card with streaming + MCP-discovered skills."""
    resp = requests.get(f"{a2a_server}/.well-known/agent-card.json", timeout=5)
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "root_agent"
    assert card.get("protocolVersion"), "agent card missing protocolVersion"
    # kagent UI uses A2A message/stream — capability must be advertised.
    assert card["capabilities"]["streaming"] is True, card["capabilities"]
    # Skills are auto-discovered from the MCPToolset by AgentCardBuilder.
    skill_ids = {s["id"] for s in card.get("skills", [])}
    assert any("get_current_time" in s for s in skill_ids), skill_ids
    assert any("convert_time" in s for s in skill_ids), skill_ids
