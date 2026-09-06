from sqlalchemy import Index

from ..base import Base
from .api_key import ApiKey
from .attachment import Attachment
from .audit_log import AuditLog
from .auth_rate_limit import AuthRateLimit
from .classifier import Classifier
from .editorial_rule import EditorialRule
from .facet import Facet
from .facet_value import FacetValue
from .inbox_message import InboxMessage
from .job import Job
from .manual_label_decision import ManualLabelDecision
from .news import News
from .news_effective_label import NewsEffectiveLabel
from .news_label import NewsLabel
from .news_source_link import NewsSourceLink
from .news_version import NewsVersion
from .outbox_event import OutboxEvent
from .processing_attempt import ProcessingAttempt
from .search_projection import SearchProjection
from .session import Session
from .setting import Setting
from .similarity_candidate import SimilarityCandidate
from .source import Source
from .submission import Submission
from .timestamp_mixin import TimestampMixin
from .upload_intent import UploadIntent
from .user import User

Index("ix_jobs_claim", Job.kind, Job.status, Job.available_at, Job.lease_until)
Index(
    "ix_outbox_claim", OutboxEvent.delivered_at, OutboxEvent.available_at, OutboxEvent.lease_until
)
Index("ix_auth_rate_limits_updated_at", AuthRateLimit.updated_at)

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "Session",
    "Source",
    "ApiKey",
    "Submission",
    "News",
    "NewsVersion",
    "NewsSourceLink",
    "Attachment",
    "UploadIntent",
    "Facet",
    "FacetValue",
    "NewsLabel",
    "NewsEffectiveLabel",
    "Classifier",
    "Job",
    "ManualLabelDecision",
    "ProcessingAttempt",
    "OutboxEvent",
    "InboxMessage",
    "SearchProjection",
    "SimilarityCandidate",
    "EditorialRule",
    "Setting",
    "AuditLog",
    "AuthRateLimit",
]
