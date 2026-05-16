# ruff: noqa
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

"""Public GitHub Documentation Agent.

A single-skill ADK A2A agent that answers questions about public GitHub
repositories by delegating retrieval to the public DeepWiki MCP server.
DeepWiki is the sole external knowledge tool — no GitHub SDK, no scraping,
no private repos.

The LLM is reached through LiteLLM with an OpenAI-compatible API. In abox
this is agentgateway's /v1 listener (which forwards Authorization from a
cluster Secret); locally it's api.openai.com directly. The same image runs
both ways — only OPENAI_API_BASE differs.
"""

import json
import os

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)

# Public DeepWiki MCP server (streamable HTTP). Override only for tests
# that need to point at a fake.
DEEPWIKI_MCP_URL = os.getenv("DEEPWIKI_MCP_URL", "https://mcp.deepwiki.com/mcp")
if not DEEPWIKI_MCP_URL:
    raise ValueError(
        "DEEPWIKI_MCP_URL must be a non-empty URL; got empty string. "
        "Unset the env var to fall back to https://mcp.deepwiki.com/mcp."
    )

# Routes LLM calls. "openai" → LiteLlm against an OpenAI-compatible /v1
# (locally api.openai.com, in cluster agentgateway). No "gemini" branch:
# abox runs OpenAI through the gateway, and adding a second model path would
# diverge from that.
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai").lower()


def _parse_headers_env(var_name: str) -> dict[str, str] | None:
    """Parse a JSON-dict env var into headers, or return None if unset/empty.

    Used to inject routing headers required by agentgateway (e.g. a tenant
    or backend selector) without baking them into the code.
    """
    raw = os.getenv(var_name)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{var_name} must be a JSON object, got: {raw!r} ({exc})"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"{var_name} must be a JSON object, got {type(parsed).__name__}"
        )
    return {str(k): str(v) for k, v in parsed.items()}


def _build_model() -> LiteLlm:
    if MODEL_PROVIDER == "openai":
        # When OPENAI_API_BASE points at agentgateway the gateway injects the
        # real Authorization header from the aire-openai-token Secret, so
        # OPENAI_API_KEY can be a placeholder. Locally it must be a real key
        # because we hit api.openai.com directly.
        kwargs: dict[str, object] = {
            "model": os.getenv("OPENAI_MODEL", "openai/gpt-4.1-mini"),
            "api_key": os.getenv("OPENAI_API_KEY"),
        }
        if api_base := os.getenv("OPENAI_API_BASE"):
            kwargs["api_base"] = api_base
        if extra_headers := _parse_headers_env("OPENAI_EXTRA_HEADERS"):
            kwargs["extra_headers"] = extra_headers
        return LiteLlm(**kwargs)

    raise ValueError(
        f"Unknown MODEL_PROVIDER={MODEL_PROVIDER!r}; expected 'openai'"
    )


INSTRUCTION = (
    "You are the Public GitHub Documentation Agent. You answer "
    "natural-language questions about *public* GitHub repositories by "
    "delegating retrieval to the DeepWiki MCP tool. DeepWiki is your only "
    "source of repository knowledge — never answer repo questions from "
    "memory.\n\n"
    "Rules — follow strictly, no exceptions:\n"
    "1. For every question about a specific public GitHub repository, you "
    "MUST call a DeepWiki MCP tool. Do not paraphrase your training data.\n"
    "2. If the question is not about a public GitHub repository (general "
    "knowledge, private repos, non-GitHub sources, opinions, anything off "
    "topic), refuse politely in one or two short plain-text sentences and "
    "do NOT call any tool.\n"
    "3. When you do answer, mention the `owner/repo` identifier the user "
    "asked about. Do not fabricate citations or contents.\n"
    "4. If DeepWiki returns an error, times out, or has no relevant "
    "content, reply in plain text explaining that DeepWiki was unreachable "
    "or returned nothing — never raise an A2A error and never invent an "
    "answer."
)

root_agent = Agent(
    name="public_github_docs_agent",
    model=_build_model(),
    description=(
        "Answers natural-language questions about public GitHub repositories. "
        "Uses DeepWiki MCP to retrieve and synthesise repository documentation."
    ),
    instruction=INSTRUCTION,
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=DEEPWIKI_MCP_URL,
                headers=_parse_headers_env("MCP_EXTRA_HEADERS"),
            ),
        ),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
