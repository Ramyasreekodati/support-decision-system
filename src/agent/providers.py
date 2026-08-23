import os
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)

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
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

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
                                "args": tc["args"]
                            }
                        })
                contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                contents.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": m["name"],
                            "response": json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
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

        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        try:
            resp = requests.post(self.endpoint, params=params, json=payload, headers=headers, timeout=20)
            if resp.status_code != 200:
                logger.error(f"Gemini API returned {resp.status_code}: {resp.text}")
                return LLMResponse(content=f"Gemini API Error {resp.status_code}: {resp.text}")

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return LLMResponse(content="No response received from Gemini.")

            content_part = candidates[0].get("content", {})
            parts = content_part.get("parts", [])

            text_parts = []
            tool_calls = []

            for i, part in enumerate(parts):
                if "text" in part:
                    text_parts.append(part["text"])
                if "functionCall" in part:
                    fn = part["functionCall"]
                    tool_calls.append(ToolCall(
                        id=f"call_{i}_{fn.get('name')}",
                        name=fn.get("name"),
                        args=fn.get("args", {})
                    ))

            full_text = "\n".join(text_parts).strip() if text_parts else None
            return LLMResponse(content=full_text, tool_calls=tool_calls, raw_response=data)

        except Exception as e:
            logger.exception("Failed to query Gemini API")
            return LLMResponse(content=f"LLM Connection Error: {str(e)}")
