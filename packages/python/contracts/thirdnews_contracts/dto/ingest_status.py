from enum import StrEnum


class IngestStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    REJECTED = "rejected"
