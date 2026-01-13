from typing import List, Optional
from pydantic import BaseModel, Field

class VerificationIssue(BaseModel):
    """单条验证错误信息。"""
    file: str
    line: Optional[int] = None
    message: str
    context: Optional[str] = None

class VerificationResult(BaseModel):
    """完整的验证结果。"""
    ok: bool
    type: str = Field(..., description="验证类型: test, lint, build")
    summary: str
    errors: List[VerificationIssue] = Field(default_factory=list)
    suggestion: Optional[str] = None

