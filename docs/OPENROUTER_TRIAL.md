# Optional OpenRouter trial

The operator-enabled cloud profile uses the existing OpenAI-compatible brief worker:

```dotenv
DIRA_LLM_URL=https://openrouter.ai/api/v1
DIRA_LLM_MODEL=qwen/qwen3.6-35b-a3b
DIRA_LLM_PROVIDER=cloud
DIRA_LLM_API_KEY=YOUR_KEY
```

Keep the real key in the ignored `.env` with mode 0600. Restart the backend after changes. No key is sent to the browser.

This profile sends up to 80 observations (text, evidence IDs, channel and timestamps) per brief to OpenRouter and its selected inference provider. Both requested briefs and the existing scheduled narrative/morning workers use it. This is connected cloud inference, not air-gapped operation. Simulation evidence remains labeled synthetic; cloud results use `cloud-llm` rather than `local-llm`.

Cloud synthesis does not enable live ASR, OCR, embeddings or feed ingestion. Those still require the local perception setup. Authentication failures, exhausted credit or timeouts return the existing extractive fallback with an error marker. To disable cloud calls, clear `DIRA_LLM_URL` and restart; to use local inference, set the local endpoint/model and `DIRA_LLM_PROVIDER=local`.

The supplied trial credential authenticated successfully on 17 November 2026. The provider reported expiration at 18 November 2026 08:44 UTC (11:44 Kuwait). A minimal model request also succeeded. Credentials are deliberately excluded from this document.

The running backend then completed a narrative job through `/api/briefs` using existing simulation evidence: `cloud-llm`, `simulated=true`, no error, 2,648 output characters. OpenRouter reasoning is disabled for these short briefs so the output budget is available for cited text. Fifteen focused backend tests passed, including cloud labeling and expired-key fallback. Real ASR/OCR inference was not part of this verification.
