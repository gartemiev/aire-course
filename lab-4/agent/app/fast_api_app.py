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

"""A2A FastAPI entrypoint for the Public GitHub Documentation Agent.

Serve with:
    uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8080

The AgentCard is built manually (not via AgentCardBuilder) because the
builder auto-explodes one skill per MCP tool — but the spec requires
exactly one skill (`answer_public_repo_questions`). Skill list is held
fixed; the underlying DeepWiki tool roster can grow without changing
the agent's advertised surface.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    EXTENDED_AGENT_CARD_PATH,
)
from fastapi import FastAPI
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from app.agent import app as adk_app
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

# Externally-reachable base URL. Locally this is the uvicorn host; in cluster
# it must be set to the gateway URL plus the HTTPRoute prefix
# (e.g. http://<gateway-ip>/a2a) so that AgentCard.url matches the path the
# gateway actually serves under.
A2A_BASE_URL = os.getenv("A2A_BASE_URL", "http://localhost:8080").rstrip("/")
# Path portion of A2A_BASE_URL drives where this app mounts its A2A routes,
# so card discovery at `{A2A_BASE_URL}/.well-known/agent-card.json` resolves
# without gateway path rewriting.
A2A_BASE_PATH = urlparse(A2A_BASE_URL).path.rstrip("/")

AGENT_VERSION = os.getenv("AGENT_VERSION", "0.1.0")

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")
artifact_service = (
    GcsArtifactService(bucket_name=logs_bucket_name)
    if logs_bucket_name
    else InMemoryArtifactService()
)

runner = Runner(
    app=adk_app,
    artifact_service=artifact_service,
    session_service=InMemorySessionService(),
)

request_handler = DefaultRequestHandler(
    agent_executor=A2aAgentExecutor(runner=runner), task_store=InMemoryTaskStore()
)


def build_agent_card() -> AgentCard:
    """Build the AgentCard advertised by this agent.

    Single fixed skill — `answer_public_repo_questions`. Skills are NOT
    auto-discovered from the MCP toolset; the agent's advertised surface
    is decoupled from DeepWiki's tool roster.
    """
    skill = AgentSkill(
        id="answer_public_repo_questions",
        name="Answer public repo questions",
        description="Answers questions about public GitHub repositories using DeepWiki MCP.",
        tags=["github", "documentation", "deepwiki"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    )
    return AgentCard(
        name="public-github-docs-agent",
        description=(
            "Answers natural-language questions about public GitHub "
            "repositories. Uses DeepWiki MCP to retrieve and synthesise "
            "repository documentation."
        ),
        url=A2A_BASE_URL,
        version=AGENT_VERSION,
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        supports_authenticated_extended_card=False,
    )


def _get_feedback_logger():
    """Lazy-init the Cloud Logging client.

    Deferred so module import stays side-effect-free for unit tests that
    have no ADC and no network. The first /feedback request pays the
    one-time setup cost.
    """
    import google.auth
    from google.cloud import logging as google_cloud_logging

    setup_telemetry()
    google.auth.default()
    return google_cloud_logging.Client().logger(__name__)


_feedback_logger = None


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    agent_card = build_agent_card()
    a2a_app = A2AFastAPIApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    a2a_app.add_routes_to_app(
        app_instance,
        agent_card_url=f"{A2A_BASE_PATH}{AGENT_CARD_WELL_KNOWN_PATH}",
        rpc_url=A2A_BASE_PATH or "/",
        extended_agent_card_url=f"{A2A_BASE_PATH}{EXTENDED_AGENT_CARD_PATH}",
    )
    yield


app = FastAPI(
    title="public-github-docs-agent",
    description="A2A agent that answers questions about public GitHub repositories via DeepWiki MCP.",
    lifespan=lifespan,
)


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    global _feedback_logger
    if _feedback_logger is None:
        _feedback_logger = _get_feedback_logger()
    _feedback_logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
