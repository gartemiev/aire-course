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

"""Unit tests for the AgentCard advertised by the FastAPI app.

No network: imports `build_agent_card` from `app.fast_api_app` and asserts
the static identity contract (single skill, plain-text modes, streaming).
"""

import importlib


def _build_card(monkeypatch, **env: str):
    """Reload fast_api_app with overridden env and return a fresh card."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import app.fast_api_app

    mod = importlib.reload(app.fast_api_app)
    return mod.build_agent_card()


def test_card_name_and_description(monkeypatch) -> None:
    card = _build_card(monkeypatch, MODEL_PROVIDER="openai")
    assert card.name == "public-github-docs-agent"
    assert "GitHub" in card.description
    assert "DeepWiki" in card.description


def test_card_advertises_single_skill(monkeypatch) -> None:
    card = _build_card(monkeypatch, MODEL_PROVIDER="openai")
    assert len(card.skills) == 1
    skill = card.skills[0]
    assert skill.id == "answer_public_repo_questions"
    assert skill.description == (
        "Answers questions about public GitHub repositories using DeepWiki MCP."
    )
    assert "text/plain" in skill.input_modes
    assert "text/plain" in skill.output_modes


def test_card_capabilities_streaming(monkeypatch) -> None:
    """kagent UI uses A2A message/stream — capability must be advertised."""
    card = _build_card(monkeypatch, MODEL_PROVIDER="openai")
    assert card.capabilities.streaming is True


def test_card_url_reads_a2a_base_url(monkeypatch) -> None:
    """AgentCard.url tracks the A2A_BASE_URL env var (default localhost:8080)."""
    card = _build_card(
        monkeypatch,
        MODEL_PROVIDER="openai",
        A2A_BASE_URL="http://gw.test.example/a2a",
    )
    assert card.url == "http://gw.test.example/a2a"


def test_card_url_default(monkeypatch) -> None:
    monkeypatch.delenv("A2A_BASE_URL", raising=False)
    card = _build_card(monkeypatch, MODEL_PROVIDER="openai")
    assert card.url == "http://localhost:8080"
