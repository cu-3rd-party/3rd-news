from pydantic import BaseModel


class TeamOut(BaseModel):
    id: str
    name: str
    display_name: str
