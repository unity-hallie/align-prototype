# Reflection MCP Server

Lightweight reflection and differential diagnosis MCP server.

- Detects provider from environment/.env (OpenAI, Anthropic, Gemini, Ollama) and uses a lightweight local model if no network provider is available.
- Stores short, bounded memories per `key` in `.local_context/reflections/<key>.jsonl`.
- Exposes MCP tools over stdio:
  - `reflection_handshake(user_key, name)`
  - `reflect(key, input)`
  - `ask(key, question)`
  - `note(key, note)`
  - `memories(key, limit?)`
  - `summarize(key)`

## Quickstart

```bash
# Run from a clone/checkout
python3 reflection_mcp/mcp_server.py
```

Register with an MCP client (example)

- Claude Desktop (config snippet):
```json
{
  "mcpServers": {
    "reflection-mcp": {
      "command": "python3",
      "args": ["/absolute/path/to/reflection_mcp/mcp_server.py"],
      "env": { "PYTHONUNBUFFERED": "1" }
    }
  }
}
```

## Environment variables

- OpenAI: `OPENAI_API_KEY`, `OPENAI_BASE_URL` (optional), `OPENAI_MODEL` (default: `gpt-4o-mini`)
- Anthropic: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` (optional), `ANTHROPIC_MODEL` (default: `claude-3-haiku-20240307`)
- Gemini: `GOOGLE_API_KEY`, `GEMINI_BASE_URL` (optional), `GEMINI_MODEL` (default: `gemini-1.5-flash`)
- Ollama: `OLLAMA_BASE_URL` or `OLLAMA_HOST`, `OLLAMA_MODEL` (default: `llama3.1:8b-instruct`)

If no provider key is found or requests fail, the server falls back to a local lightweight reflector.

## File layout

- `reflection_mcp/mcp_server.py`: MCP stdio server
- `reflection_mcp/provider.py`: provider detection + HTTP client
- `utils/reflection_memory.py`: shared local memory store (JSONL)

## License

Proprietary/internal by default. Add a license if open-sourcing.

