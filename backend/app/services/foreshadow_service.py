from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
from sqlmodel import Session, select
from datetime import datetime

from app.db.models import ForeshadowItem as ForeshadowItemModel


class ForeshadowService:
    def __init__(self, session: Session):
        self.session = session

    def suggest(self, text: str) -> Dict[str, Any]:
        """
        極簡啓發式：
        - 捕捉“將要/準備/打算/誓要/必須”等後接短語作爲待完成目標
        - 捕捉以『劍/刀/戒/符/印/丹/陣/甲/鼎/珠/鏡』爲後綴的名詞作爲可疑道具
        - 粗略抽取2-4字的人名候選（排除常見功能詞）
        """
        if not isinstance(text, str):
            text = str(text or "")
        goals: List[str] = []
        items: List[str] = []
        persons: List[str] = []

        # 目標
        for m in re.findall(r"(將要|準備|打算|誓要|必須)([^。？！\n]{2,20})", text):
            frag = (m[0] + m[1]).strip()
            if frag and frag not in goals:
                goals.append(frag)

        # 道具
        for m in re.findall(r"([\u4e00-\u9fa5]{1,8})(劍|刀|戒|符|印|丹|陣|甲|鼎|珠|鏡)", text):
            frag = (m[0] + m[1]).strip()
            if frag and frag not in items:
                items.append(frag)

        # 人名（粗略）
        stopwords = {"什麼", "但是", "因爲", "然後", "雖然", "可是", "不會", "看看", "我們", "你們", "他們", "以及"}
        for m in re.findall(r"([\u4e00-\u9fa5]{2,4})", text):
            if m and 2 <= len(m) <= 4 and m not in stopwords:
                if m not in persons:
                    persons.append(m)
        persons = persons[:10]

        return {
            "goals": goals[:8],
            "items": items[:8],
            "persons": persons,
        }

    # --- CRUD via DB ---
    def list(self, project_id: int, status: Optional[str] = None) -> List[ForeshadowItemModel]:
        stmt = select(ForeshadowItemModel).where(ForeshadowItemModel.project_id == project_id)
        if status:
            stmt = stmt.where(ForeshadowItemModel.status == status)
        items = self.session.exec(stmt.order_by(ForeshadowItemModel.status.desc(), ForeshadowItemModel.created_at.desc())).all()
        return items

    def register(self, project_id: int, entries: List[Dict[str, Any]]) -> List[ForeshadowItemModel]:
        out: List[ForeshadowItemModel] = []
        for it in entries:
            title = str(it.get('title') or '').strip()
            if not title:
                continue
            item = ForeshadowItemModel(
                project_id=project_id,
                chapter_id=it.get('chapter_id'),
                title=title,
                type=str(it.get('type') or 'other') or 'other',
                note=it.get('note'),
                status='open',
            )
            self.session.add(item)
            out.append(item)
        if out:
            self.session.commit()
            for i in out:
                self.session.refresh(i)
        return out

    def resolve(self, project_id: int, item_id: str | int) -> Optional[ForeshadowItemModel]:
        item = self.session.get(ForeshadowItemModel, item_id)
        if not item or item.project_id != project_id:
            return None
        if item.status != 'resolved':
            item.status = 'resolved'
            item.resolved_at = datetime.utcnow()
            self.session.add(item)
            self.session.commit()
            self.session.refresh(item)
        return item

    def delete(self, project_id: int, item_id: str | int) -> bool:
        item = self.session.get(ForeshadowItemModel, item_id)
        if not item or item.project_id != project_id:
            return False
        self.session.delete(item)
        self.session.commit()
        return True 