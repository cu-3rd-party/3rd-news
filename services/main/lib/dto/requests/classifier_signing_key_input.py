from pydantic import BaseModel, Field


class ClassifierSigningKeyInput(BaseModel):
    signing_public_key: str = Field(min_length=1, max_length=20_000)
