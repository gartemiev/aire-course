"""Unit tests for the time-agent Phoenix / OpenInference tracing bootstrap.

Mirrors lab-5/time-mcp-server/tests/unit/test_tracing.py: clears the
`PHOENIX_DISABLE_REGISTER` opt-out, monkey-patches `phoenix.otel.register`
to a stub, reloads `app.agent`, and asserts the production startup hook
calls `register()` with `auto_instrument=True`.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock


def _reload_app_agent():
    # Force a clean reload so the module-level bootstrap runs again.
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)
    return importlib.import_module("app.agent")


def test_bootstrap_calls_phoenix_register_with_auto_instrument(monkeypatch) -> None:
    monkeypatch.delenv("PHOENIX_DISABLE_REGISTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://test.example/v1/traces")
    monkeypatch.setenv("PHOENIX_PROJECT_NAME", "time-agent")
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_BASE", "http://example.test/v1")

    stub_provider = MagicMock(name="TracerProvider")
    stub_provider.get_tracer.return_value = MagicMock(name="Tracer")
    register_mock = MagicMock(name="register", return_value=stub_provider)

    import phoenix.otel  # noqa: F401  # ensure module is loaded

    monkeypatch.setattr("phoenix.otel.register", register_mock)

    agent_mod = _reload_app_agent()

    register_mock.assert_called_once()
    kwargs = register_mock.call_args.kwargs
    assert kwargs.get("auto_instrument") is True
    assert kwargs.get("project_name") == "time-agent"
    assert kwargs.get("endpoint") == "http://test.example/v1/traces"
    assert agent_mod.TRACER_PROVIDER is stub_provider


def test_disabled_env_skips_register(monkeypatch) -> None:
    monkeypatch.setenv("PHOENIX_DISABLE_REGISTER", "1")
    monkeypatch.setenv("MODEL_PROVIDER", "openai")

    register_mock = MagicMock(name="register")
    monkeypatch.setattr("phoenix.otel.register", register_mock)

    agent_mod = _reload_app_agent()

    register_mock.assert_not_called()
    assert agent_mod.TRACER_PROVIDER is None

    decorator = agent_mod.tracer.tool(name="agent.test")
    sentinel = object()
    assert decorator(sentinel) is sentinel
