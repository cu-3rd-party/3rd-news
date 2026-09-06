from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Measurement:
    index: int
    ingest_status: str
    submission_id: str
    news_id: str
    news_status: str
    accepted_ms: float
    pipeline_ms: float
