from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.security import OAuth2PasswordRequestForm

from api.schemas import TokenResponse, UserResponse
from api.security import AuthenticatedUser, check_rbac, create_access_token
from api.services import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _service(request: Request) -> AuthService:
    return request.app.state.auth_service


def _unavailable_error(service: AuthService) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=service.initialization_error or "MySQL RBAC auth is unavailable",
    )


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """用户名密码登录，返回前端后续请求要携带的 Bearer Token。"""
    service = _service(request)
    if not service.available:
        raise _unavailable_error(service)

    user = service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token, expires_in = create_access_token(user)
    return TokenResponse(access_token=access_token, expires_in=expires_in, scopes=user.scopes)


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: AuthenticatedUser = Security(check_rbac)):
    """前端启动时用来验证 token 是否仍然有效。"""
    return UserResponse(username=current_user.username, scopes=current_user.scopes)


@router.get("/rbac")
async def read_rbac_snapshot(
    request: Request,
    _current_user: AuthenticatedUser = Security(check_rbac, scopes=["conversations"]),
):
    """查看当前 RBAC 种子数据，便于本地调试用户、角色和权限关系。"""
    service = _service(request)
    if not service.available:
        raise _unavailable_error(service)
    return service.list_rbac_snapshot()
