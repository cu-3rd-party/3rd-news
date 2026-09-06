from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClassifierIdentity:
    slug: str
    name: str
    version: str
    description: str


IDENTITY = ClassifierIdentity(
    slug="ai-openai-compatible",
    name="OpenAI-compatible classifier",
    version="2.0.0",
    description="Uses an OpenAI-compatible endpoint; defaults to Ollama qwen3:0.6b.",
)
