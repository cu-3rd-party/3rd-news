from pydantic import BaseModel, Field


class UploadPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=1000)
    content_type: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
