from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BookStageItem(BaseModel):
    """拆書階段條目（用於階段劃分/合併）"""

    stage_name: str = Field(description="階段名稱，例如：穿越與萌芽")
    chapter_start: int = Field(description="階段起始章節號（全書序號，從1開始）", ge=1)
    chapter_end: int = Field(description="階段結束章節號（全書序號，從1開始）", ge=1)
    stage_outline: str = Field(
        description=(
            "階段故事大綱（Markdown 文本），必須包含：階段起因、階段目標、衝突與阻力、"
            "關鍵事件鏈（至少3條）、角色關係/能力變化、階段結果與下一階段鉤子；"
            "要求細緻、可執行，重點體現主角與主要角色變化。"
        )
    )

    stage_summary: Optional[str] = Field(
        default=None,
        description="階段劇情概述（400~800字），用流暢敘事概述該階段的劇情推進",
    )


class BookStageChunkPlan(BaseModel):
    """單個章節上下文塊的階段劃分結果"""

    stages: List[BookStageItem] = Field(
        default_factory=list,
        description="當前上下文塊內建議的階段列表（可1~N個）"
    )


class BookStageFinalPlan(BaseModel):
    """全書最終階段規劃結果"""

    stages: List[BookStageItem] = Field(
        default_factory=list,
        description="全書最終階段劃分（需滿足最大階段數約束）"
    )
