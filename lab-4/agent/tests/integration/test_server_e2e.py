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

"""A2A end-to-end smoke test.

Boots `app.fast_api_app:app` on a random local port and asserts the
well-known agent card is served with the fixed identity, single skill
(`answer_public_repo_questions`), and streaming capability.

Skipped unless DEEPWIKI_MCP_URL is reachable: the agent module's import
opens an MCPToolset against DeepWiki, so the subprocess can't start
without it. That's intentional — the BYO container must fail loud if
the MCP server is missing.
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
    """JSON-RPC initialize against DeepWiki — accept only a real MCP response."""
    url = os.getenv("DEEPWIKI_MCP_URL", "https://mcp.deepwiki.com/mcp")
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
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
    except RequestException:
        return False
    if resp.status_code >= 400:
        return False
    return '"result"' in resp.text or '"error"' in resp.text


pytestmark = pytest.mark.skipif(
    not _mcp_reachable(),
    reason="DeepWiki MCP not reachable; fast_api_app cannot start without it",
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
    env.setdefault("OPENAI_API_KEY", "placeholder-test")
    env["A2A_BASE_URL"] = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.fast_api_app:app",
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
    """Card has the right identity + exactly one skill + streaming capability."""
    resp = requests.get(f"{a2a_server}/.well-known/agent-card.json", timeout=5)
    assert resp.status_code == 200
    card = resp.json()

    assert card["name"] == "public-github-docs-agent"
    assert card.get("protocolVersion"), "agent card missing protocolVersion"
    # kagent UI uses A2A message/stream — capability must be advertised.
    assert card["capabilities"]["streaming"] is True, card["capabilities"]

    skills = card.get("skills", [])
    assert len(skills) == 1, f"expected exactly one skill, got {len(skills)}: {skills}"
    skill = skills[0]
    assert skill["id"] == "answer_public_repo_questions", skill
    assert "text/plain" in skill["inputModes"], skill
    assert "text/plain" in skill["outputModes"], skill
