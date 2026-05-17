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

"""Unit tests for the Public GitHub Documentation Agent wiring.

No network: only asserts the agent is constructed with the right MCP toolset
and that MODEL_PROVIDER selects the right model class.

Every test goes through `_reload_agent_with_env`, which uses pytest's
`monkeypatch` so env mutations are torn down at test end and don't leak into
sibling tests (e.g. the e2e subprocess in tests/integration/test_server_e2e.py
inheriting a fake DEEPWIKI_MCP_URL).
"""

import importlib

import pytest
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)


def _reload_agent_with_env(monkeypatch, **env: str):
    """Set env vars (scoped to the test) and reload app.agent."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import app.agent

    return importlib.reload(app.agent)


def test_root_agent_has_deepwiki_mcp_toolset(monkeypatch) -> None:
    mod = _reload_agent_with_env(
        monkeypatch,
        MODEL_PROVIDER="openai",
    )

    toolsets = [t for t in mod.root_agent.tools if isinstance(t, McpToolset)]
    assert len(toolsets) == 1

    toolset = toolsets[0]
    assert isinstance(toolset._connection_params, StreamableHTTPConnectionParams)
    assert toolset._connection_params.url == "https://mcp.deepwiki.com/mcp"


def test_no_other_tool_sources(monkeypatch) -> None:
    """Only one MCP toolset; no other tools, no GitHub clients, no tokens."""
    mod = _reload_agent_with_env(monkeypatch, MODEL_PROVIDER="openai")
    tools = mod.root_agent.tools
    # Exactly one tool, exactly the DeepWiki MCP toolset.
    assert len(tools) == 1
    assert isinstance(tools[0], McpToolset)
    # No second MCP toolset (would indicate a stray tool source).
    assert sum(1 for t in tools if isinstance(t, McpToolset)) == 1

    # Catch accidental leakage of GitHub-SDK-style modules / tokens onto the
    # agent module surface. This is a coarse check, not a security boundary.
    forbidden_attrs = {
        "github",
        "Github",
        "GITHUB_TOKEN",
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "octokit",
    }
    leaked = forbidden_attrs.intersection(vars(mod).keys())
    assert not leaked, f"agent module leaked GitHub-SDK-style names: {leaked}"


def test_openai_provider_uses_litellm(monkeypatch) -> None:
    mod = _reload_agent_with_env(
        monkeypatch,
        MODEL_PROVIDER="openai",
        OPENAI_API_BASE="http://example.test/v1",
    )
    from google.adk.models.lite_llm import LiteLlm

    assert isinstance(mod.root_agent.canonical_model, LiteLlm)


def test_unknown_provider_raises(monkeypatch) -> None:
    with pytest.raises(ValueError, match="Unknown MODEL_PROVIDER"):
        _reload_agent_with_env(monkeypatch, MODEL_PROVIDER="bogus")


def test_mcp_extra_headers_passed_through(monkeypatch) -> None:
    mod = _reload_agent_with_env(
        monkeypatch,
        MODEL_PROVIDER="openai",
        MCP_EXTRA_HEADERS='{"X-Tenant": "acme", "X-Route-Tier": "premium"}',
    )
    toolset = next(t for t in mod.root_agent.tools if isinstance(t, McpToolset))
    assert toolset._connection_params.headers == {
        "X-Tenant": "acme",
        "X-Route-Tier": "premium",
    }


def test_invalid_headers_json_raises(monkeypatch) -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        _reload_agent_with_env(
            monkeypatch,
            MODEL_PROVIDER="openai",
            OPENAI_EXTRA_HEADERS="not-json",
        )
