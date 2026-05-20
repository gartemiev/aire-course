# Copyright 2025 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse

# Configuration
DEFAULT_SANDBOX_PORT = 8888
DEFAULT_NAMESPACE = "default"
DEFAULT_PROXY_TIMEOUT = 180.0
DEFAULT_CLUSTER_DOMAIN = "cluster.local"

# RFC 7230 §6.1 hop-by-hop headers — must not be forwarded by intermediaries.
# We strip these in both directions plus Host (request) and Content-Length /
# Content-Encoding (response) so StreamingResponse can re-frame the body
# without the client trusting upstream's length/encoding headers.
HOP_BY_HOP_HEADERS = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
})


def _get_proxy_timeout() -> float:
    raw = os.environ.get("PROXY_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_PROXY_TIMEOUT
    try:
        value = float(raw)
    except (ValueError, TypeError):
        print(f"WARNING: Invalid PROXY_TIMEOUT_SECONDS='{raw}', "
              f"falling back to {DEFAULT_PROXY_TIMEOUT}s")
        return DEFAULT_PROXY_TIMEOUT
    if value <= 0:
        print(f"WARNING: PROXY_TIMEOUT_SECONDS must be positive, got {value}, "
              f"falling back to {DEFAULT_PROXY_TIMEOUT}s")
        return DEFAULT_PROXY_TIMEOUT
    return value


def _get_cluster_domain() -> str:
    cluster_domain = os.environ.get("CLUSTER_DOMAIN")
    if cluster_domain is None:
        return DEFAULT_CLUSTER_DOMAIN
    if cluster_domain == "":
        print("WARNING: CLUSTER_DOMAIN must not be an empty string, "
              f"falling back to {DEFAULT_CLUSTER_DOMAIN}")
        return DEFAULT_CLUSTER_DOMAIN
    return cluster_domain


cluster_domain = _get_cluster_domain()
proxy_timeout = _get_proxy_timeout()

print(f"Sandbox router configured with proxy timeout: {proxy_timeout}s")
print(f"Sandbox router configured with cluster_domain: {cluster_domain}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Single shared AsyncClient: connection pooling + a tidy aclose() on
    # shutdown so we don't leak sockets when uvicorn restarts under
    # `--reload` or rolls during a Deployment update.
    async with httpx.AsyncClient(timeout=proxy_timeout) as client:
        app.state.client = client
        yield


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def health_check():
    """A simple health check endpoint that always returns 200 OK."""
    return {"status": "ok"}


@app.api_route("/{full_path:path}", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
async def proxy_request(request: Request, full_path: str):
    """
    Receives all incoming requests, determines the target sandbox from headers,
    and asynchronously proxies the request to it.
    """
    sandbox_id = request.headers.get("X-Sandbox-ID")
    if not sandbox_id:
        raise HTTPException(
            status_code=400, detail="X-Sandbox-ID header is required.")

    # Dynamic discovery via headers
    namespace = request.headers.get("X-Sandbox-Namespace", DEFAULT_NAMESPACE)
    
    # Sanitize namespace to prevent DNS injection
    if not namespace.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid namespace format.")

    try:
        port = int(request.headers.get("X-Sandbox-Port", DEFAULT_SANDBOX_PORT))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid port format.")

    # Dynamic routing: route by Pod IP if provided by client, otherwise fallback to DNS name
    pod_ip = request.headers.get("X-Sandbox-Pod-IP")
    if pod_ip:
        target_host = pod_ip
    else:
        # Construct the K8s internal DNS name
        target_host = f"{sandbox_id}.{namespace}.svc.{cluster_domain}"

    target_url = str(
        request.url.replace(scheme="http", hostname=target_host, port=port)
    )

    print(f"Proxying request for sandbox '{sandbox_id}' to URL: {target_url}")

    try:
        # Strip Host (httpx will set it for the new target) and hop-by-hop
        # headers (RFC 7230 §6.1) from the outbound request.
        headers = {
            key: value
            for (key, value) in request.headers.items()
            if key.lower() != "host" and key.lower() not in HOP_BY_HOP_HEADERS
        }

        client = request.app.state.client
        req = client.build_request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=request.stream()
        )

        resp = await client.send(req, stream=True)

        # Strip hop-by-hop headers from the upstream response. Also drop
        # Content-Length / Content-Encoding: httpx decodes any transport
        # encoding before aiter_bytes() yields, and StreamingResponse will
        # re-frame the body for the downstream client, so the upstream
        # values no longer describe what we're sending.
        response_headers = {
            key: value
            for (key, value) in resp.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
            and key.lower() not in {"content-length", "content-encoding"}
        }

        return StreamingResponse(
            content=resp.aiter_bytes(),
            status_code=resp.status_code,
            headers=response_headers
        )
    except httpx.ConnectError as e:
        print(
            f"ERROR: Connection to sandbox at {target_url} failed. Error: {e}")
        raise HTTPException(
            status_code=502, detail=f"Could not connect to the backend sandbox: {sandbox_id}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred in the proxy.")