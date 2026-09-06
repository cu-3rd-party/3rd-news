from .contract_model import ContractModel


class ClassifyAttachment(ContractModel):
    kind: str
    media_id: str | None = None
    mime: str | None = None
    filename: str | None = None
    caption: str | None = None
    extracted_text: str | None = None
