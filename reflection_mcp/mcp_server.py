#!/usr/bin/env python3
"""
Reflection MCP Server

Lightweight MCP stdio server that:
- Detects provider from .env (OpenAI, Anthropic, Gemini, Ollama),
  defaults to a local lightweight reflector (no network required)
- Tools:
  - reflection_handshake(user_key, name)
  - reflect(key, input)
  - ask(key, question)
  - note(key, note)
  - memories(key, limit?)
  - summarize(key)

Outputs MCP-style JSON-RPC responses with content text.
"""
import json
import sys
from typing import Any, Dict, List

from reflection_mcp.provider import load_env, detect_provider, get_completion
from utils.reflection_memory import MemoryEntry, load_memories, append_memory, summarize_memories


def mcp_result_text(text: str) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
    }


def list_tools() -> Dict[str, Any]:
    tools = [
        {"name": "reflection_handshake", "description": "Register or verify user", "inputSchema": {"type": "object", "properties": {"user_key": {"type": "string"}, "name": {"type": "string"}}, "required": ["user_key", "name"]}},
        {"name": "reflect", "description": "Reflect on input and store brief memory", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "input": {"type": "string"}}, "required": ["key", "input"]}},
        {"name": "ask", "description": "Answer a question concisely and store memory", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "question": {"type": "string"}}, "required": ["key", "question"]}},
        {"name": "note", "description": "Store a short note to memory", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "note": {"type": "string"}}, "required": ["key", "note"]}},
        {"name": "memories", "description": "Retrieve recent memories", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}, "limit": {"type": "integer"}} , "required": ["key"]}},
        {"name": "summarize", "description": "Summarize recent memories", "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}},
    ]
    return {"tools": tools}


class ReflectionServer:
    def __init__(self):
        self.env = load_env()
        self.cfg = detect_provider(self.env)

    def handle_call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name == 'reflection_handshake':
            user_key = args.get('user_key', '')
            nm = args.get('name', '')
            return mcp_result_text(json.dumps({"user_key": user_key, "name": nm, "provider": self.cfg.provider, "model": self.cfg.model}))

        if name == 'ask':
            key = args.get('key', '')
            q = args.get('question', '')
            ans = get_completion(self.cfg, f"Answer concisely. Q: {q}")
            append_memory(key, MemoryEntry(ts=_now(), kind='ask', prompt=q, response=ans, meta={"provider": self.cfg.provider, "model": self.cfg.model}))
            return mcp_result_text(ans)

        if name == 'reflect':
            key = args.get('key', '')
            inp = args.get('input', '')
            ans = get_completion(self.cfg, f"Reflect briefly on: {inp}\nReturn key points and a next step.")
            append_memory(key, MemoryEntry(ts=_now(), kind='reflect', prompt=inp, response=ans, meta={"provider": self.cfg.provider, "model": self.cfg.model}))
            return mcp_result_text(ans)

        if name == 'note':
            key = args.get('key', '')
            note = args.get('note', '')
            append_memory(key, MemoryEntry(ts=_now(), kind='note', prompt=note, response='', meta={}))
            return mcp_result_text("noted")

        if name == 'memories':
            key = args.get('key', '')
            limit = int(args.get('limit', 20))
            mems = load_memories(key, limit)
            text = json.dumps([m.__dict__ for m in mems], ensure_ascii=False)
            return mcp_result_text(text)

        if name == 'summarize':
            key = args.get('key', '')
            text = summarize_memories(key)
            return mcp_result_text(text)

        raise ValueError(f"Unknown tool: {name}")


def _now():
    import datetime
    return datetime.datetime.utcnow().isoformat() + 'Z'


def main():
    server = ReflectionServer()
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
            method = req.get('method')
            _id = req.get('id')
            if method == 'initialize':
                resp = {"jsonrpc": "2.0", "id": _id, "result": {"serverInfo": {"name": "reflection-mcp", "version": "0.1.0"}}}
            elif method == 'tools/list':
                resp = {"jsonrpc": "2.0", "id": _id, "result": list_tools()}
            elif method == 'tools/call':
                params = req.get('params') or {}
                name = params.get('name')
                args = params.get('arguments') or {}
                try:
                    result = server.handle_call(name, args)
                    resp = {"jsonrpc": "2.0", "id": _id, "result": result}
                except Exception as e:
                    resp = {"jsonrpc": "2.0", "id": _id, "error": {"code": -32603, "message": f"Internal error: {e}"}}
            else:
                resp = {"jsonrpc": "2.0", "id": _id, "error": {"code": -32601, "message": "Method not found"}}
        except Exception as e:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == '__main__':
    main()

