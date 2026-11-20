from fastapi import APIRouter, Request, Response

from app.observability.metrics import CONTENT_TYPE

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    return Response(request.app.state.metrics.render(), media_type=CONTENT_TYPE)