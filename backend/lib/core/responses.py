import orjson
from starlette.responses import Response


class OrjsonResponse(Response):
    media_type = "application/json"

    def render(self, content: object) -> bytes:
        return orjson.dumps(content)
