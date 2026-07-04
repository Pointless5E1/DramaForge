from __future__ import annotations

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
	text: str = Field(..., description="待校驗文本")
	facts_structured: Optional[Dict[str, Any]] = Field(default=None, description="結構化事實子圖（relation_summaries等）")


class Issue(BaseModel):
	type: str
	message: str
	position: List[int] | None = None


class FixSuggestion(BaseModel):
	range: List[int] | None = None
	replacement: str


class CheckResponse(BaseModel):
	issues: List[Issue]
	suggested_fixes: List[FixSuggestion] 