from pydantic import BaseModel


class AutoPublishInput(BaseModel):
    enabled: bool
