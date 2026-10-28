from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class PaginationParams(BaseModel):
    limit: int = 20
    offset: int = 0

