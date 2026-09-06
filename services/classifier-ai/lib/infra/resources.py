import asyncio
from dataclasses import dataclass, field

from ..core.config import Settings
from ..interactor.interfaces.clients.provider import ProviderClient
from ..interactor.use_cases.ai_classification import AIClassification
from .clients.ollama import OllamaClient
from .clients.openai import OpenAIClient


@dataclass(slots=True)
class AppResources:
    classifier: AIClassification
    provider: ProviderClient
    background: set[asyncio.Task[None]] = field(default_factory=set)

    @classmethod
    def create(cls, settings: Settings) -> AppResources:
        provider: ProviderClient
        if settings.provider_protocol == "ollama-native":
            provider = OllamaClient(settings)
        else:
            settings.require_openai_key()
            provider = OpenAIClient(settings)
        return cls(classifier=AIClassification(settings, provider), provider=provider)

    async def close(self) -> None:
        pending = tuple(self.background)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
