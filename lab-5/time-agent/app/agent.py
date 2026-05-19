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

import json
import os
from contextlib import contextmanager
from typing import Any

import phoenix.otel
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)

# --- Phoenix / OpenInference tracing bootstrap -------------------------------
#
# Runs before `root_agent = Agent(...)` is constructed below so the OTel
# auto-instrumentation hooks installed by `register()` see the agent /
# LiteLLM / MCP toolset calls. With `auto_instrument=True` and
# `openinference-instrumentation-mcp` on the classpath, the outbound MCP
# tool call propagates trace context to the server side, joining both
# spans into one Phoenix trace.
#
# Tests set PHOENIX_DISABLE_REGISTER=1 (see tests/conftest.py) to swap in
# the no-op tracer so reloads of app.agent in test_agent_wiring.py don't
# attempt OTLP connections. tests/unit/test_tracing.py clears that env
# var and reloads this module to assert register() was called with
# `auto_instrument=True`.
PROJECT_NAME = os.environ.get("PHOENIX_PROJECT_NAME", "time-agent")


class _NoOpToolDecorator:
    def __call__(self, fn):  # type: ignore[no-untyped-def]
        return fn


class _NoOpTracer:
    """Tracer stub for tests; keeps the `.tool(...)` decorator API callable."""

    def tool(self, name: str | None = None, **kwargs: Any) -> _NoOpToolDecorator:
        return _NoOpToolDecorator()

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        yield None


if os.environ.get("PHOENIX_DISABLE_REGISTER"):
    TRACER_PROVIDER: Any = None
    tracer: Any = _NoOpTracer()
else:
    TRACER_PROVIDER = phoenix.otel.register(
        project_name=PROJECT_NAME,
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
        auto_instrument=True,
    )
    tracer = TRACER_PROVIDER.get_tracer("time-agent")


# Where the MCP server lives. Locally: port-forward agentgateway-external 8080:80
# (or the time-mcp svc 3000:3000). In-cluster (kagent BYO): the gateway DNS.
TIME_MCP_URL = os.getenv("TIME_MCP_URL", "http://localhost:8080/mcp")

# Model provider: "openai" routes through agentgateway's /v1 (mirrors the
# deployed Declarative agent). "gemini" uses Vertex AI directly.
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai").lower()


def _parse_headers_env(var_name: str) -> dict[str, str] | None:
    """Parse a JSON-dict env var into headers, or return None if unset/empty.

    Used to inject routing headers required by agentgateway (e.g. a tenant
    or backend selector) without baking them into the code. Unset → no
    headers added, so the same image runs unchanged against a plain LLM or
    MCP endpoint locally.
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
        raise ValueError(f"{var_name} must be a JSON object, got {type(parsed).__name__}")
    return {str(k): str(v) for k, v in parsed.items()}


def _build_model():
    if MODEL_PROVIDER == "openai":
        from google.adk.models.lite_llm import LiteLlm

        # If OPENAI_API_BASE is unset, fall through to LiteLLM's default
        # (api.openai.com). When set (e.g. to the agentgateway URL), the
        # gateway injects the real Authorization header from aire-openai-token
        # so OPENAI_API_KEY can be a placeholder.
        kwargs = {
            "model": os.getenv("OPENAI_MODEL", "openai/gpt-4.1-mini"),
            "api_key": os.getenv("OPENAI_API_KEY"),
        }
        if api_base := os.getenv("OPENAI_API_BASE"):
            kwargs["api_base"] = api_base
        if extra_headers := _parse_headers_env("OPENAI_EXTRA_HEADERS"):
            kwargs["extra_headers"] = extra_headers
        return LiteLlm(**kwargs)

    if MODEL_PROVIDER == "gemini":
        import google.auth
        from google.adk.models import Gemini
        from google.genai import types

        _, project_id = google.auth.default()
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
        return Gemini(
            model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            retry_options=types.HttpRetryOptions(attempts=3),
        )

    raise ValueError(
        f"Unknown MODEL_PROVIDER={MODEL_PROVIDER!r}; expected 'openai' or 'gemini'"
    )


root_agent = Agent(
    name="root_agent",
    model=_build_model(),
    instruction=(
        "You are a time-and-timezone assistant. You have two tools: "
        "get_current_time and convert_time.\n\n"
        "Rules — follow strictly, no exceptions:\n"
        "1. NEVER ask the user clarifying questions. Do not request user input.\n"
        "2. If the user asks for the current time without specifying a timezone, "
        "immediately call get_current_time with timezone=\"UTC\" and return the "
        "result. Do not ask which timezone.\n"
        "3. If the user asks to convert a time and either the source or target "
        "timezone is missing, assume UTC for whichever is missing and call "
        "convert_time. Do not ask.\n"
        "4. Always answer in one turn: tool call, then final answer. No "
        "follow-up questions to the user."
    ),
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=TIME_MCP_URL,
                headers=_parse_headers_env("MCP_EXTRA_HEADERS"),
            ),
            tool_filter=["get_current_time", "convert_time"],
        ),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
