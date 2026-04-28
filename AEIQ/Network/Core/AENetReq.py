from pydantic import BaseModel, Field
from typing import Any, Optional, Dict


class AENetReq(BaseModel):
    """网络请求数据"""
    path: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = None
    question: Optional[Dict[str, Any]] = None
    llm_types: Optional[list] = None
    method: Optional[str] = None
    requestId: Optional[str] = Field(None, alias="request_id")

    def to_bytes(self) -> bytes:
        return self.model_dump_json(by_alias=True, exclude_none=True).encode('utf-8')

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AENetReq':
        return cls.model_validate_json(data.decode('utf-8'))

    model_config = {"populate_by_name": True}




