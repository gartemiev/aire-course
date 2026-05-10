# Lab 1: Deploying Basic Agentic Infrastructure

## Beginner

1. Install `agentgateway` locally: https://agentgateway.dev/docs/standalone/latest/deployment/binary/

2. Choose an LLM provider: https://agentgateway.dev/docs/standalone/latest/llm/providers/

3. Configure `config.yaml`: https://agentgateway.dev/docs/standalone/latest/tutorials/llm-gateway/

4. Start the gateway and access the UI: http://localhost:15000/ui/

5. Verify access to the LLM and explore the fundamental capabilities of **Backends** and **Policy**.

## Experienced

1. Complete the Beginner tasks, but deploy `agentgateway` as a Helm deployment in a Kubernetes cluster.

2. Configure Kubernetes `Secrets` and `ConfigMaps` for API keys and configuration.

3. Deploy `kagent`: https://kagent.dev/docs/kagent/getting-started/quickstart

4. Configure model routing through `agentgateway`.

5. Verify that any built-in agent is working correctly.

## Max

1. Complete the Experienced tasks, but use Gateway API: https://agentgateway.dev/docs/kubernetes/main/about/gateway-api/

### Research 1: Review the S&T ADR Project — DevOps Bot/Agent

Review and evaluate the ADR for the **S&T: DevOps Bot/Agent** project.

1. Prepare your questions about the project.
2. Suggest possible improvements.
3. Propose potential solutions.
