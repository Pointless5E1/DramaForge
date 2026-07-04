from typing import Any, AsyncIterator, Dict

from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select

from app.db.models import Project
from ...registry import register_node
from ..base import BaseNode


class SelectProjectInput(BaseModel):
    """選擇項目輸入"""

    project_id: int | None = Field(
        default=None,
        description="項目ID",
        json_schema_extra={"x-component": "ProjectSelect"},
    )
    project_name: str | None = Field(
        default=None,
        description="項目名稱（當 project_id 爲空時按名稱解析，名稱和ID提供一個即可）",
        json_schema_extra={"x-component": "ProjectSelect"},
    )


class SelectProjectOutput(BaseModel):
    """選擇項目輸出"""

    project_id: int = Field(..., description="項目ID")
    project: Dict[str, Any] = Field(..., description="項目對象")


@register_node
class SelectProjectNode(BaseNode[SelectProjectInput, SelectProjectOutput]):
    node_type = "Logic.SelectProject"
    category = "logic"
    label = "選擇項目"
    description = "選擇並輸出一個項目，可以根據名字、ID來獲取具體的項目，返回結果中包括項目ID"

    input_model = SelectProjectInput
    output_model = SelectProjectOutput

    async def execute(self, inputs: SelectProjectInput) -> AsyncIterator[SelectProjectOutput]:
        session = self.context.session

        project = None
        if inputs.project_id is not None:
            project = session.get(Project, inputs.project_id)

        if project is None and inputs.project_name:
            project = session.exec(
                select(Project).where(Project.name == inputs.project_name)
            ).first()
            if project is None:
                candidates = session.exec(select(Project)).all()
                lowered = inputs.project_name.lower()
                matches = [
                    item
                    for item in candidates
                    if lowered in (item.name or "").lower()
                ]
                if len(matches) == 1:
                    project = matches[0]
                elif len(matches) > 1:
                    raise ValueError(
                        f"項目名匹配到多個候選: {inputs.project_name}"
                    )

        if not project:
            raise ValueError(
                f"項目不存在: id={inputs.project_id}, name={inputs.project_name}"
            )

        logger.info(f"[SelectProject] 選擇項目: {project.name} (id={project.id})")

        yield SelectProjectOutput(
            project_id=project.id,
            project={
                "id": project.id,
                "name": project.name,
                "description": project.description,
            },
        )
