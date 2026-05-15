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
card is served with the expected skills. Does not call the LLM.
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
    # Make MCP/LLM URLs harmless — we never invoke the model in this test.
    env.setdefault("TIME_MCP_URL", f"http://127.0.0.1:{_free_port()}/mcp")
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
    """Smoke test: BYO entrypoint boots and serves the A2A well-known card.

    The card's per-tool skills come from MCP tool discovery, which requires a
    reachable MCP server — out of scope for this test (see test_agent.py for
    the with-MCP integration). Here we only assert the card structure.
    """
    resp = requests.get(f"{a2a_server}/.well-known/agent-card.json", timeout=5)
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "root_agent"
    assert card.get("protocolVersion"), "agent card missing protocolVersion"
    # kagent UI uses A2A message/stream — capability must be advertised.
    assert card["capabilities"]["streaming"] is True, card["capabilities"]
    skill_ids = {s["id"] for s in card.get("skills", [])}
    assert {"get_current_time", "convert_time"}.issubset(skill_ids), skill_ids
