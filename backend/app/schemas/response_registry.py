from __future__ import annotations

from typing import Dict, Any

# 統一集中導出所有需要在 OpenAPI 中暴露的響應/嵌套模型
from app.schemas.wizard import (
    Text,
	WorldBuilding, Blueprint,
	VolumeOutline, ChapterOutline,
	SpecialAbilityResponse, OneSentence, ParagraphOverview,
	CharacterCard, SceneCard, StoryLine, StageLine, 
	Tags, WorldviewTemplate, Chapter,
	ScreenplayTags, ScreenplayOneSentence, ScreenplayOverview,
	ScreenplayWorldBuilding, ScreenplayBlueprint, ScreenplayEpisodeOutline,
	ScreenplayStageLine, ScreenplaySegmentOutline, ScreenplaySegmentContent,
 WritingGuide, ReviewResultCardContent
)
from app.schemas.entity import ConceptCard, ItemCard, OrganizationCard
from app.schemas.workflow_models import BookStageChunkPlan, BookStageFinalPlan


RESPONSE_MODEL_MAP: Dict[str, Any] = {
    "Text": Text,
	'Tags': Tags,
	'SpecialAbilityResponse': SpecialAbilityResponse,
	'OneSentence': OneSentence,
	'ParagraphOverview': ParagraphOverview,
	'WorldBuilding': WorldBuilding,
	'WorldviewTemplate': WorldviewTemplate,
	'Blueprint': Blueprint,
	# 使用未包裝模型
	'VolumeOutline': VolumeOutline,
 	'WritingGuide': WritingGuide,
    'ReviewResultCardContent': ReviewResultCardContent,
	'ChapterOutline': ChapterOutline,
	'Chapter': Chapter,
	'ScreenplayTags': ScreenplayTags,
	'ScreenplayOneSentence': ScreenplayOneSentence,
	'ScreenplayOverview': ScreenplayOverview,
	'ScreenplayWorldBuilding': ScreenplayWorldBuilding,
	'ScreenplayBlueprint': ScreenplayBlueprint,
	'ScreenplayEpisodeOutline': ScreenplayEpisodeOutline,
	'ScreenplayStageLine': ScreenplayStageLine,
	'ScreenplaySegmentOutline': ScreenplaySegmentOutline,
	'ScreenplaySegmentContent': ScreenplaySegmentContent,
	# 基礎schema，自動包含在OpenAPI中
	'CharacterCard': CharacterCard,
	'SceneCard': SceneCard,
	'OrganizationCard': OrganizationCard,
	'ItemCard': ItemCard,
	'ConceptCard': ConceptCard,
	# 顯式導出嵌套類型，便於前端字段樹解析
	'StageLine': StageLine,
	'StoryLine': StoryLine,
	# 工作流專用結構模型
	'BookStageChunkPlan': BookStageChunkPlan,
	'BookStageFinalPlan': BookStageFinalPlan,
} 
