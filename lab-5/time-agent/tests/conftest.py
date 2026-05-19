"""Pytest bootstrap for time-agent tests.

Importing `app.agent` triggers a `phoenix.otel.register()` call so the
production process wires its tracer at startup. Unit tests don't need
that and the OTLP exporter logs noisy connection errors when the
collector isn't reachable, so we default to the no-op tracer here.
`tests/unit/test_tracing.py` explicitly clears this env var and reloads
`app.agent` to verify the real bootstrap path.
"""

import os

os.environ.setdefault("PHOENIX_DISABLE_REGISTER", "1")
