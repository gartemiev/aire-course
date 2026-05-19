# Lab 5

## Beginner

1. **Agent Sandbox:** Review the examples:  
   https://agent-sandbox.sigs.k8s.io/docs/use-cases/examples/

2. Implement any example, or the recommended one:  
   **Network Policies**  
   https://agent-sandbox.sigs.k8s.io/docs/use-cases/examples/network-policies/

3. Review **Tracing and Evaluating** and complete the **Colab LangChain Application** tutorial:  
   https://colab.research.google.com/github/Arize-ai/phoenix/blob/main/tutorials/tracing/langchain_tracing_tutorial.ipynb

---

## Experienced

1. Deploy **Arize Phoenix** in `abox`:  
   https://arize.com/docs/phoenix/self-hosting/deployment-options/kubernetes-helm

2. Implement telemetry collection in **Agent Sandbox**:  
   https://agent-sandbox.sigs.k8s.io/docs/sandbox/metrics/

3. Instrument tracing for your own **MCP server** and send traces to **Phoenix**:  
   https://arize.com/docs/phoenix/integrations/python/mcp-tracing

---

## Max

1. Configure telemetry collection from **agentgateway** to **Phoenix**:  
   https://agentgateway.dev/docs/kubernetes/latest/tutorials/telemetry/

2. Review how to manage **Agent Sandbox** using the SDK:  
   https://agent-sandbox.sigs.k8s.io/docs/use-cases/examples/code-interpreter-agent-on-adk/

---

## Additional Tasks

These tasks can be completed when `abox` is already deployed. They are implemented using several Kubernetes manifests.

1. **API Key case on agentgateway**  
   https://agentgateway.dev/docs/kubernetes/latest/security/apikey/

2. **Guardrails case on agentgateway**  
   https://agentgateway.dev/docs/kubernetes/latest/llm/guardrails/webhook/guardrails/


# Solutions

1-2. In terms of https://github.com/kubernetes-sigs/agent-sandbox - I didn't include it into abox Flux flow since my assumption
was that these steps are mostly focused on familiarizing with it functionality and possbile use cases.

I've deployed suggested example without any issues. Key ides which I got is: 

Agent Sandbox is not an agent by itself. It is a Kubernetes-native sandbox/runtime layer where an agent can perform risky, stateful, or interactive actions.

For your context with Kagent / A2A / MCP, I would think about it like this:

```
Kagent Agent / BYO Agent
   |
   | decides what to do
   | calls MCP tools / public MCP server / internal tools
   |
   +--> Agent Sandbox
          |
          +--> execute code
          +--> run shell commands
          +--> work with files
          +--> browser/computer use
          +--> temporary workspace
```

In other words, the agent remains the “brain” and the orchestration layer, while the Sandbox is the “hands” or working environment where the agent can safely do things.

When the agent can live inside the Sandbox: 

This makes sense when We need a long-lived personal or project-specific agent environment, for example: one sandbox per user / project / repo.

Inside it, We may have:
* agent process
* workspace files
* git repo
* installed tools
* local cache
* memory/state
* browser session

