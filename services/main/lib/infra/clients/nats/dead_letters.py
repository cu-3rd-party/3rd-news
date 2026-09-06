import json

from lib.core.config import Settings
from lib.interactor.interfaces.clients.dead_letters import DeadLetterClient

from nats.js.errors import NotFoundError

from .jetstream import JetStreamBroker, StreamSettings


class DeadLetters(DeadLetterClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def list(self, *, after: int, limit: int) -> dict:
        settings = self.settings
        async with JetStreamBroker(
            settings.broker_url,
            settings=StreamSettings(
                name=settings.broker_stream, subjects=(f"{settings.broker_subject_prefix}.>",)
            ),
        ) as broker:
            stream = f"{settings.broker_stream}_DLQ"
            try:
                info = await broker.jetstream.stream_info(stream)
            except NotFoundError:
                return {"items": [], "cursor": after}
            items = []
            cursor = max(after, info.state.first_seq - 1)
            while cursor < info.state.last_seq and len(items) < limit:
                cursor += 1
                try:
                    message = await broker.jetstream.get_msg(stream, seq=cursor)
                except NotFoundError:
                    continue
                items.append({"sequence": cursor, **json.loads(message.data or b"{}")})
            return {"items": items, "cursor": cursor}
