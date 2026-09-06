from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClassifierIdentity:
    slug: str
    name: str
    version: str
    description: str


IDENTITY = ClassifierIdentity(
    slug="regex",
    name="Regex / keyword classifier",
    version="2.0.0",
    description="Applies taxonomy synonyms and match_patterns.",
)
