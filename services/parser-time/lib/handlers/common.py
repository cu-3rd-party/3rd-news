from fastapi import HTTPException

from ..domain.entities.channel_ref import ChannelRef
from ..interactor.interfaces.clients.parser_application import ParserApplication


def resources_from(holder: list[ParserApplication]) -> ParserApplication:
    if not holder:
        raise HTTPException(status_code=503, detail="parser is starting")
    return holder[0]


def parse_ref(value: str) -> ChannelRef:
    try:
        return ChannelRef.parse(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
