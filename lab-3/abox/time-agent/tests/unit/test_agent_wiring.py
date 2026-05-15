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

"""Unit tests for time-agent wiring.

No network: only asserts the agent is constructed with the right MCP toolset
and that MODEL_PROVIDER selects the right model class.
"""

import importlib
import os

import pytest

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)


def _reload_agent_with_env(**env: str):
    for key, value in env.items():
        os.environ[key] = value
    import app.agent

    return importlib.reload(app.agent)


def test_root_agent_has_mcp_toolset_with_filter() -> None:
    mod = _reload_agent_with_env(
        MODEL_PROVIDER="openai",
        TIME_MCP_URL="http://example.test/mcp",
    )

    toolsets = [t for t in mod.root_agent.tools if isinstance(t, McpToolset)]
    assert len(toolsets) == 1

    toolset = toolsets[0]
    assert isinstance(toolset._connection_params, StreamableHTTPConnectionParams)
    assert toolset._connection_params.url == "http://example.test/mcp"
    assert sorted(toolset.tool_filter or []) == ["convert_time", "get_current_time"]


def test_openai_provider_uses_litellm() -> None:
    mod = _reload_agent_with_env(
        MODEL_PROVIDER="openai",
        OPENAI_API_BASE="http://example.test/v1",
    )
    from google.adk.models.lite_llm import LiteLlm

    assert isinstance(mod.root_agent.canonical_model, LiteLlm)


def test_unknown_provider_raises() -> None:
    os.environ["MODEL_PROVIDER"] = "bogus"
    with pytest.raises(ValueError, match="Unknown MODEL_PROVIDER"):
        import app.agent

        importlib.reload(app.agent)
    os.environ["MODEL_PROVIDER"] = "openai"
    import app.agent

    importlib.reload(app.agent)


def test_mcp_extra_headers_passed_through() -> None:
    mod = _reload_agent_with_env(
        MODEL_PROVIDER="openai",
        MCP_EXTRA_HEADERS='{"X-Tenant": "acme", "X-Route-Tier": "premium"}',
    )
    toolset = next(t for t in mod.root_agent.tools if isinstance(t, McpToolset))
    assert toolset._connection_params.headers == {
        "X-Tenant": "acme",
        "X-Route-Tier": "premium",
    }


def test_mcp_extra_headers_unset_means_none() -> None:
    os.environ.pop("MCP_EXTRA_HEADERS", None)
    mod = _reload_agent_with_env(MODEL_PROVIDER="openai")
    toolset = next(t for t in mod.root_agent.tools if isinstance(t, McpToolset))
    assert toolset._connection_params.headers is None


def test_openai_extra_headers_passed_through() -> None:
    mod = _reload_agent_with_env(
        MODEL_PROVIDER="openai",
        OPENAI_EXTRA_HEADERS='{"X-Backend": "openai-prod"}',
    )
    assert mod.root_agent.canonical_model._additional_args.get("extra_headers") == {
        "X-Backend": "openai-prod"
    }


def test_invalid_headers_json_raises() -> None:
    os.environ["OPENAI_EXTRA_HEADERS"] = "not-json"
    with pytest.raises(ValueError, match="must be a JSON object"):
        import app.agent

        importlib.reload(app.agent)
    os.environ.pop("OPENAI_EXTRA_HEADERS", None)
    import app.agent

    importlib.reload(app.agent)
