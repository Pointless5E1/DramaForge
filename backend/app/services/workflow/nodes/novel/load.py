from typing import Any, Dict, List, Optional, AsyncIterator
import os
import re
from loguru import logger
from pydantic import Field, BaseModel

from ...registry import register_node
from ..base import BaseNode


class NovelLoadInput(BaseModel):
    """Novel.Load 節點輸入 - 所有參數都在這裏"""
    root_path: str = Field(
        ..., 
        description="小說根目錄路徑",
        json_schema_extra={"x-component": "DirectorySelect"}
    )
    file_pattern: str = Field(
        r".*\.(txt|md)$", 
        description="文件名匹配正則"
    )
    volume_pattern: str = Field(
        r"第[一二三四五六七八九十0-9]+[卷部紀]", 
        description="分卷文件夾匹配正則"
    )
    chapter_pattern: str = Field(
        r"第([零一二三四五六七八九十百千0-9]+)章", 
        description="章節名匹配正則（用於提取序號）"
    )


class NovelLoadOutput(BaseModel):
    """Novel.Load 節點輸出"""
    chapter_list: List[Dict[str, Any]] = Field(..., description="章節元數據列表")
    volume_list: List[str] = Field(..., description="分卷列表")


@register_node
class NovelLoadNode(BaseNode[NovelLoadInput, NovelLoadOutput]):
    node_type = "Novel.Load"
    category = "novel"
    label = "加載小說"
    description = "掃描小說目錄，生成章節列表元數據"
    
    input_model = NovelLoadInput
    output_model = NovelLoadOutput

    async def execute(self, inputs: NovelLoadInput) -> AsyncIterator[NovelLoadOutput]:
        """執行小說加載"""
        # 驗證目錄存在
        if not os.path.exists(inputs.root_path):
            raise ValueError(f"目錄不存在: {inputs.root_path}")
            
        chapter_list = []
        volumes = set()
        
        # 編譯正則
        try:
            file_re = re.compile(inputs.file_pattern)
            vol_re = re.compile(inputs.volume_pattern)
            chap_re = re.compile(inputs.chapter_pattern)
        except Exception as e:
            raise ValueError(f"正則編譯失敗: {e}")

        logger.info(f"[Novel.Load] 開始掃描: {inputs.root_path}")
        
        # 遍歷目錄
        for dirpath, dirnames, filenames in os.walk(inputs.root_path):
            # 確定當前分卷
            rel_path = os.path.relpath(dirpath, inputs.root_path)
            current_volume = "默認分卷"
            
            if rel_path != ".":
                parts = rel_path.split(os.sep)
                if parts:
                    potential_vol = parts[0]
                    if vol_re.search(potential_vol):
                        current_volume = potential_vol
                    else:
                        current_volume = potential_vol

            volumes.add(current_volume)
            
            for fname in filenames:
                if not file_re.match(fname):
                    continue
                    
                full_path = os.path.join(dirpath, fname)
                title = os.path.splitext(fname)[0]
                
                # 嘗試提取章節序號
                idx = 0
                match = chap_re.search(title)
                if match:
                    if match.groups():
                        try:
                            idx = int(match.group(1))
                        except ValueError:
                            pass
                    else:
                        num_match = re.search(r"\d+", match.group())
                        if num_match:
                            idx = int(num_match.group())
                
                # 構建元數據
                meta = {
                    "title": title,
                    "path": full_path,
                    "volume": current_volume,
                    "index": idx,
                    "filename": fname
                }
                chapter_list.append(meta)

        # 排序
        chapter_list.sort(key=lambda x: (x['volume'], x['index'], x['title']))
        
        # 提取分卷列表並進行自然排序
        volumes_set = set(item['volume'] for item in chapter_list)
        
        # 自然排序函數
        def natural_sort_key(text):
            """將文本轉換爲可排序的鍵，支持中文數字和阿拉伯數字"""
            import re
            
            # 中文數字映射
            chinese_num_map = {
                '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
                '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
                '百': 100, '千': 1000
            }
            
            def chinese_to_num(s):
                """簡單的中文數字轉換（支持一到九十九）"""
                if not s:
                    return 0
                if s in chinese_num_map:
                    return chinese_num_map[s]
                # 處理 "十X" 或 "X十" 或 "X十X"
                if '十' in s:
                    parts = s.split('十')
                    if len(parts) == 2:
                        left = chinese_num_map.get(parts[0], 1 if not parts[0] else 0)
                        right = chinese_num_map.get(parts[1], 0)
                        return left * 10 + right
                return 0
            
            # 提取數字部分
            match = re.search(r'第([一二三四五六七八九十百千0-9]+)[卷部紀]', text)
            if match:
                num_str = match.group(1)
                # 嘗試阿拉伯數字
                if num_str.isdigit():
                    return int(num_str)
                # 嘗試中文數字
                return chinese_to_num(num_str)
            return 0
        
        volumes = sorted(list(volumes_set), key=natural_sort_key)
        
        logger.info(f"[Novel.Load] 掃描完成，共找到 {len(chapter_list)} 章節，{len(volumes)} 分卷")
        
        # 直接返回類型化的輸出
        yield NovelLoadOutput(
            chapter_list=chapter_list,
            volume_list=volumes
        )
