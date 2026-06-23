from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    scopes: list[str]


class UserResponse(BaseModel):
    username: str
    scopes: list[str]
