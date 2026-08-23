import os
import json
import math
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import requests
import pathlib

logger = logging.getLogger(__name__)

# Auto-load local .env file if present
env_path = pathlib.Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    try:
        with open(env_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    val = v.strip().strip("\"'")
                    if val:
                        os.environ[k.strip()] = val
    except Exception:
        pass

def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert float('nan'), float('inf'), and non-serializable objects to None."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    elif hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj

@dataclass
class ToolCall:
    id: str
    name: str
    args: Dict[str, Any]

@dataclass
class LLMResponse:
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMResponse:
        pass

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.6-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            try:
                import streamlit as st
                if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
                    self.api_key = str(st.secrets["GEMINI_API_KEY"])
            except Exception:
                pass
        self.model = model
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    def set_api_key(self, api_key: str):
        self.api_key = (api_key or "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    def _convert_tools_to_gemini_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        function_declarations = []
        for t in tools:
            decl = {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}})
            }
            function_declarations.append(decl)
        return [{"function_declarations": function_declarations}]

    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMResponse:
        if not self.is_available():
            raise ValueError("GEMINI_API_KEY is not configured or empty.")

        contents = []
        for m in messages:
            role = m["role"]
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": m["content"]}]})
            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                if m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        parts.append({
                            "functionCall": {
                                "name": tc["name"],
                                "args": sanitize_for_json(tc["args"])
                            }
                        })
                contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                clean_response = sanitize_for_json(m["content"])
                if isinstance(clean_response, str):
                    try:
                        clean_response = json.loads(clean_response)
                        clean_response = sanitize_for_json(clean_response)
                    except Exception:
                        pass
                contents.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": m["name"],
                            "response": clean_response if isinstance(clean_response, dict) else {"result": clean_response}
                        }
                    }]
                })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 1024
            }
        }

        if tools:
            payload["tools"] = self._convert_tools_to_gemini_format(tools)
            payload["toolConfig"] = {
                "functionCallingConfig": {
                    "mode": "AUTO"
                }
            }

        payload = sanitize_for_json(payload)

        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        try:
            resp = requests.post(
                self.endpoint,
                headers=headers,
                params=params,
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                return LLMResponse(content="No response generated.", raw_response=data)

            candidate = candidates[0]
            content_part = candidate.get("content", {})
            parts = content_part.get("parts", [])

            text_content = ""
            tool_calls = []

            for part in parts:
                if "text" in part:
                    text_content += part["text"]
                if "functionCall" in part:
                    fn = part["functionCall"]
                    tool_calls.append(ToolCall(
                        id=f"call_{len(tool_calls)+1}",
                        name=fn["name"],
                        args=fn.get("args", {})
                    ))

            return LLMResponse(
                content=text_content.strip() if text_content else None,
                tool_calls=tool_calls,
                raw_response=data
            )
        except Exception as e:
            logger.exception("Gemini API call failed")
            raise RuntimeError(f"Gemini API Error: {str(e)}") from e
