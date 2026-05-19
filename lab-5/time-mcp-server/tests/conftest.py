"""Pytest bootstrap for time-mcp-server tests.

Importing `core.server` triggers a `phoenix.otel.register()` call so the
production process wires its tracer at startup. Plain unit tests don't
need that and the OTLP exporter logs noisy connection errors when the
collector isn't reachable, so we default to the no-op tracer here. The
`tests/unit/test_tracing.py` test explicitly clears this env var and
reloads `core.server` to verify the real bootstrap path.
"""

import os

os.environ.setdefault("PHOENIX_DISABLE_REGISTER", "1")
