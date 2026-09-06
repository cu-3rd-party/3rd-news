from typing import Any

import aiohttp

from ...core.config import Settings
from ...interactor.interfaces.clients.provider import ProviderClient
from .response_reader import bounded_json


class OllamaClient(ProviderClient):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self._settings.openai_timeout_s)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(f"{self._settings.ollama_base_url}/api/chat", json=payload) as response,
        ):
            body = await bounded_json(response, self._settings.max_provider_response_bytes)
            if response.status >= 400:
                error = body.get("error")
                message = error.get("message") if isinstance(error, dict) else None
                raise RuntimeError(
                    f"provider returned {response.status}: {message or 'request failed'}"
                )
            return body
