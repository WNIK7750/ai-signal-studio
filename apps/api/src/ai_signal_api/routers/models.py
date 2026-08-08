from fastapi import APIRouter, HTTPException, Request, Response, status
from ai_signal_api.modules.models.service import (
    ModelConfigurationError,
    ModelConfigurationService,
)
from ai_signal_api.schemas import (
    ModelConnectionRead,
    ModelConfigCreate,
    ModelConfigPatch,
    ModelConfigRead,
    ProviderConfigRead,
)


router = APIRouter(prefix="/api", tags=["models"])


def _service(request: Request) -> ModelConfigurationService:
    return request.app.state.model_configuration


def _error_status(error: ModelConfigurationError) -> int:
    if error.code == "MODEL-001":
        return status.HTTP_404_NOT_FOUND
    if error.code in {"MODEL-004", "MODEL-007", "MODEL-009"}:
        return status.HTTP_409_CONFLICT
    if error.code == "SECRET-004":
        return status.HTTP_401_UNAUTHORIZED
    if error.code == "PROVIDER-004":
        return status.HTTP_504_GATEWAY_TIMEOUT
    if error.code == "PROVIDER-005":
        return status.HTTP_429_TOO_MANY_REQUESTS
    if error.code in {"MODEL-005", "PROVIDER-003"}:
        return status.HTTP_502_BAD_GATEWAY
    return status.HTTP_422_UNPROCESSABLE_CONTENT


@router.get("/providers", response_model=list[ProviderConfigRead])
def list_providers(request: Request) -> list[ProviderConfigRead]:
    return [
        ProviderConfigRead.model_validate(provider)
        for provider in _service(request).list_providers()
    ]


@router.get("/models", response_model=list[ModelConfigRead])
def list_models(
    request: Request,
) -> list[ModelConfigRead]:
    return [
        ModelConfigRead.model_validate(model)
        for model in _service(request).list_models()
    ]


@router.post(
    "/models",
    response_model=ModelConfigRead,
    status_code=status.HTTP_201_CREATED,
)
def create_model(
    payload: ModelConfigCreate,
    request: Request,
) -> ModelConfigRead:
    try:
        model = _service(request).create_model(payload.model_dump())
    except ModelConfigurationError as error:
        raise HTTPException(
            status_code=_error_status(error),
            detail=str(error),
        ) from error
    return ModelConfigRead.model_validate(model)


@router.patch("/models/{model_id}", response_model=ModelConfigRead)
def update_model(
    model_id: str,
    payload: ModelConfigPatch,
    request: Request,
) -> ModelConfigRead:
    try:
        model = _service(request).update_model(
            model_id,
            payload.model_dump(exclude_unset=True),
        )
    except ModelConfigurationError as error:
        raise HTTPException(
            status_code=_error_status(error),
            detail=str(error),
        ) from error
    return ModelConfigRead.model_validate(model)


@router.delete(
    "/models/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_model(model_id: str, request: Request) -> Response:
    try:
        _service(request).delete_model(model_id)
    except ModelConfigurationError as error:
        error_status = (
            status.HTTP_404_NOT_FOUND
            if error.code == "MODEL-001"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=error_status,
            detail=str(error),
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/models/{model_id}/activate", response_model=ModelConfigRead)
def activate_model(
    model_id: str,
    request: Request,
) -> ModelConfigRead:
    try:
        model = _service(request).activate_model(model_id)
    except ModelConfigurationError as error:
        raise HTTPException(
            status_code=_error_status(error),
            detail=str(error),
        ) from error
    return ModelConfigRead.model_validate(model)


@router.post(
    "/models/{model_id}/activate-search",
    response_model=ModelConfigRead,
)
def activate_search_model(
    model_id: str,
    request: Request,
) -> ModelConfigRead:
    try:
        model = _service(request).activate_search_model(model_id)
    except ModelConfigurationError as error:
        raise HTTPException(
            status_code=_error_status(error),
            detail=str(error),
        ) from error
    return ModelConfigRead.model_validate(model)


@router.post(
    "/models/{model_id}/test",
    response_model=ModelConnectionRead,
)
def test_model_connection(
    model_id: str,
    request: Request,
) -> ModelConnectionRead:
    try:
        _service(request).test_model_connection(
            model_id,
            request.app.state.model_chat,
        )
    except ModelConfigurationError as error:
        raise HTTPException(
            status_code=_error_status(error),
            detail=str(error),
        ) from error
    return ModelConnectionRead(
        status="ok",
        message="MODEL-000（连接成功）",
    )
