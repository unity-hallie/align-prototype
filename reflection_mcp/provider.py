#!/usr/bin/env python3
import os
from dataclasses import dataclass
from typing import Optional
import json
import urllib.request
import urllib.error
import socket


def load_env(path: Optional[str] = None) -> dict:
    env = {}
    # Merge OS env first
    env.update(os.environ)
    # Then load .env if present
    dotenv = path or os.path.join(os.getcwd(), '.env')
    try:
        if os.path.exists(dotenv):
            with open(dotenv, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        env.setdefault(k.strip(), v.strip())
    except Exception:
        pass
    return env


@dataclass
class ProviderConfig:
    provider: str  # openai|anthropic|gemini|ollama|local
    model: str
    endpoint: Optional[str] = None  # base URL or host if applicable
    env: Optional[dict] = None      # raw env for keys


def detect_provider(env: dict) -> ProviderConfig:
    # Prefer explicit lightweight models
    if env.get('OPENAI_API_KEY'):
        return ProviderConfig('openai', env.get('OPENAI_MODEL', 'gpt-4o-mini'), env.get('OPENAI_BASE_URL', 'https://api.openai.com/v1'), env)
    if env.get('ANTHROPIC_API_KEY'):
        return ProviderConfig('anthropic', env.get('ANTHROPIC_MODEL', 'claude-3-haiku-20240307'), env.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com'), env)
    if env.get('GOOGLE_API_KEY'):
        return ProviderConfig('gemini', env.get('GEMINI_MODEL', 'gemini-1.5-flash'), env.get('GEMINI_BASE_URL', 'https://generativelanguage.googleapis.com'), env)
    if env.get('OLLAMA_HOST') or env.get('OLLAMA_BASE_URL'):
        return ProviderConfig('ollama', env.get('OLLAMA_MODEL', 'llama3.1:8b-instruct'), env.get('OLLAMA_HOST') or env.get('OLLAMA_BASE_URL') or 'http://localhost:11434', env)
    return ProviderConfig('local', 'mini-reflector', None, env)


class LocalModel:
    name = 'mini-reflector'

    @staticmethod
    def complete(prompt: str) -> str:
        # Extremely lightweight heuristic response
        prompt = (prompt or '').strip()
        if not prompt:
            return "No prompt provided."
        # Provide a short, structured reflection
        lines = []
        lines.append("Answer (concise): " + prompt[:200])
        lines.append("Key points: " + ", ".join([w for w in prompt.split()[:6]]))
        lines.append("Next step: Clarify assumptions and outline 2 actions.")
        return "\n".join(lines)


def _http_post_json(url: str, headers: dict, payload: dict, timeout: float = 8.0) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={**headers, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8') or '{}')
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        raise RuntimeError(f"HTTP error: {e}")


def get_completion(cfg: ProviderConfig, prompt: str) -> str:
    provider = (cfg.provider or 'local').lower()
    try:
        if provider == 'openai':
            base = cfg.endpoint or 'https://api.openai.com/v1'
            url = f"{base.rstrip('/')}/chat/completions"
            key = cfg.env.get('OPENAI_API_KEY') if cfg.env else None
            headers = {'Authorization': f'Bearer {key}'}
            payload = {
                'model': cfg.model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': float(cfg.env.get('OPENAI_TEMPERATURE', '0.2')) if cfg.env else 0.2,
                'max_tokens': int(cfg.env.get('OPENAI_MAX_TOKENS', '400')) if cfg.env else 400,
            }
            data = _http_post_json(url, headers, payload)
            return (data.get('choices') or [{}])[0].get('message', {}).get('content') or LocalModel.complete(prompt)

        if provider == 'anthropic':
            base = cfg.endpoint or 'https://api.anthropic.com'
            url = f"{base.rstrip('/')}/v1/messages"
            key = cfg.env.get('ANTHROPIC_API_KEY') if cfg.env else None
            headers = {
                'x-api-key': key,
                'anthropic-version': cfg.env.get('ANTHROPIC_VERSION', '2023-06-01') if cfg.env else '2023-06-01',
            }
            payload = {
                'model': cfg.model,
                'max_tokens': int(cfg.env.get('ANTHROPIC_MAX_TOKENS', '400')) if cfg.env else 400,
                'messages': [{'role': 'user', 'content': prompt}],
            }
            data = _http_post_json(url, headers, payload)
            content = (data.get('content') or [{}])[0]
            if isinstance(content, dict):
                return content.get('text') or LocalModel.complete(prompt)
            return LocalModel.complete(prompt)

        if provider == 'gemini':
            base = cfg.endpoint or 'https://generativelanguage.googleapis.com'
            key = cfg.env.get('GOOGLE_API_KEY') if cfg.env else None
            model = cfg.model
            url = f"{base.rstrip('/')}/v1beta/models/{model}:generateContent?key={key}"
            headers = {}
            payload = {
                'contents': [{'parts': [{'text': prompt}]}]
            }
            data = _http_post_json(url, headers, payload)
            cands = data.get('candidates') or []
            if cands:
                parts = (cands[0].get('content') or {}).get('parts') or []
                if parts:
                    return parts[0].get('text') or LocalModel.complete(prompt)
            return LocalModel.complete(prompt)

        if provider == 'ollama':
            base = cfg.endpoint or 'http://localhost:11434'
            url = f"{base.rstrip('/')}/api/generate"
            headers = {}
            payload = {'model': cfg.model, 'prompt': prompt, 'stream': False}
            data = _http_post_json(url, headers, payload)
            return data.get('response') or LocalModel.complete(prompt)
    except Exception:
        # Any network/parse issue falls back to local
        pass

    # Default local lightweight reflection
    return LocalModel.complete(prompt)
