"""Public contracts of the 3rd-news platform.

Anyone writing a parser or a classifier — in this repo or in a completely
separate one — depends only on this package (or on the equivalent JSON
described in `docs/contracts/`). Nothing here imports the main service.
"""

from .taxonomy import FacetType, FacetValueSchema, FacetSchema, Taxonomy
from .ingest import (
    AttachmentKind,
    AttachmentInput,
    NewsSubmission,
    IngestResult,
    IngestStatus,
)
from .classifier import (
    ClassifierManifest,
    ClassifyNews,
    ClassifyAttachment,
    ClassifyOptions,
    ClassifyRequest,
    ClassifyResponse,
    LabeledExample,
    ProposedLabel,
    CallbackResult,
)
from .news import Attachment, Label, NewsItem, NewsPage
from .signing import sign_payload, verify_signature, SIGNATURE_HEADER, TIMESTAMP_HEADER
from .client import IngestClient, IngestError

__all__ = [
    "FacetType",
    "FacetValueSchema",
    "FacetSchema",
    "Taxonomy",
    "AttachmentKind",
    "AttachmentInput",
    "NewsSubmission",
    "IngestResult",
    "IngestStatus",
    "ClassifierManifest",
    "ClassifyNews",
    "ClassifyAttachment",
    "ClassifyOptions",
    "ClassifyRequest",
    "ClassifyResponse",
    "LabeledExample",
    "ProposedLabel",
    "CallbackResult",
    "Attachment",
    "Label",
    "NewsItem",
    "NewsPage",
    "sign_payload",
    "verify_signature",
    "SIGNATURE_HEADER",
    "TIMESTAMP_HEADER",
    "IngestClient",
    "IngestError",
]

CONTRACT_VERSION = "1.0"
