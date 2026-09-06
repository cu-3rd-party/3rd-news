from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubmissionIdentity:
    source: str | None
    external_id: str | None
    idempotency_key: str | None

    def __post_init__(self) -> None:
        has_source_identity = bool(self.source and self.external_id)
        if not has_source_identity and not self.idempotency_key:
            raise ValueError("source and external_id, or an idempotency key, is required")
