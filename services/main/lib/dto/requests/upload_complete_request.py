import uuid

from pydantic import BaseModel


class UploadCompleteRequest(BaseModel):
    upload_id: uuid.UUID
