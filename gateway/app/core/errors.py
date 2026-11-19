from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str, type_: str = "invalid_request_error"):
        self.status, self.message, self.code, self.type_ = status, message, code, type_


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        body = {"error": {"message": exc.message, "type": exc.type_, "code": exc.code}}
        return JSONResponse(status_code=exc.status, content=body)