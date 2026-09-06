from fastapi.responses import JSONResponse


def internal_error(request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "request_id": request_id},
    )
