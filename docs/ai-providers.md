# AI providers: external now, private when a company needs it

Decision (2026-10-20): use an external model for now (Claude API), but keep the AI behind an
interface so a company can run Machine Forge privately.

Machine designs, BOMs and supplier prices are sensitive company IP. Pick the deployment by where
the data is allowed to go:

| Option | Data leaves the company? | Quality | Setup | How in Machine Forge |
|---|---|---|---|---|
| **Claude API** (default) | Yes, to Anthropic (API data is not used for training by default; zero-data-retention agreements exist) | Best | API key | `MF_LLM_PROVIDER=anthropic` |
| **Claude in the company's cloud**: Amazon Bedrock, Google Vertex AI, Microsoft Foundry | Stays in the company's cloud tenancy and contracts | Best | Cloud account, model access | Small change: use `AnthropicBedrockMantle` / `AnthropicVertex` / `AnthropicFoundry` client in `llm/anthropic_provider.py`, and drop `fallbacks` (not available there) |
| **Company Azure OpenAI or another hosted endpoint** | Stays within that contract | Model-dependent | Endpoint + key | `MF_LLM_PROVIDER=openai_compatible` |
| **On-premise open model**: Ollama, vLLM, LM Studio | No | Lower; needs a strong model (≥ 70B class) for reliable designs | GPU server | `MF_LLM_PROVIDER=openai_compatible`, `MF_OPENAI_BASE_URL=http://server:11434/v1` |

## Configuration

```ini
# Claude (default)
MF_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
MF_ANTHROPIC_MODEL=claude-opus-5-5
MF_ANTHROPIC_EFFORT=high          # low | medium | high | xhigh | max

# Private: Ollama on a local server
MF_LLM_PROVIDER=openai_compatible
MF_OPENAI_BASE_URL=http://gpu-server:11434/v1
MF_OPENAI_MODEL=llama3.3:70b
MF_OPENAI_API_KEY=                # empty for Ollama

# No AI: demo engine
MF_LLM_PROVIDER=mock
```

## Notes on the Claude provider

- Model `claude-opus-5-5` with adaptive thinking; `MF_ANTHROPIC_EFFORT` trades cost/latency
  against design quality. `high` is the default because machine design is hard reasoning.
- Structured outputs guarantee the answer is valid JSON for the design schema.
- Streaming is used so long generations don't hit HTTP timeouts. A first design typically takes
  tens of seconds to a few minutes.
- The system prompt is cached (it is identical on every call).
- Server-side refusal fallback (`fallbacks: "default"`) is enabled: if a safety classifier declines
  a request, the API retries it on its recommended fallback model.

## Quality with local models

Open models follow the JSON schema less reliably. The provider retries once and sends back the
validation error. Expect thinner designs (fewer components, fewer specs) than with Claude. Before
committing to a private deployment, run the same problem statements through both and compare.
