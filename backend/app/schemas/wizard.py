from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional, List, Tuple, Any, Union

from .entity import CharacterCard as CharacterCard  # 以完整角色卡替換簡化模型
from .entity import SceneCard as SceneCard
from .entity import OrganizationCard as OrganizationCard
from .entity import EntityType as EntityType


class Text(BaseModel):
    '''
    通用的文本模型，自由存儲各種內容
    '''
    content: str = Field(description="任意文本內容，需使用/轉換爲markdown格式文本")

# --- Schemas for Tags ---

class Tags(BaseModel):
    """
    統一的標籤模型。
    """
    theme: str = Field(default="", description="主題類別，格式: 大類-子類")
    audience: Literal['通用','男生', '女生'] = Field(default='通用', description="目標讀者")
    narrative_person: Literal['第一人稱', '第三人稱'] = Field(default='第三人稱', description="寫作人稱（第一人稱/第三人稱）")
    story_tags: List[Tuple[str, Literal['低權重', '中權重', '高權重']]] = Field(default=[], description="類別標籤及權重檔位（低/中/高）")
    affection: str = Field(default="", description="情感關係標籤")


class SpecialAbility(BaseModel):
    name: str = Field(description="金手指的名稱")
    description: str = Field(description="金手指的具體描述")


class SpecialAbilityResponse(BaseModel):
    """0: 根據tags設計金手指的請求模型"""
    special_abilities_thinking: str = Field(description="從標籤到金手指的創作思考過程。",examples=["示例輸出，僅供學習思考方式，不要被具體內容影響：根據標籤“重生”和“無敵流”，我需要設計一個讓主角能夠不斷嘗試、不斷變強，最終達到無敵狀態的金手指。僅僅重生一次不足以支撐“無敵流”的長期發展，因此，將“重生”特性深化爲“無限復活並回溯時間”的能力，每次復活都能保留經驗和記憶，這既符合“重生”的特點，又能爲主角的“無敵”之路提供邏輯支撐。同時，結合“異世大陸”和“文明推演”的背景，這種能力能夠讓主角在面對未知世界時，通過反覆試錯來積累知識和經驗，從而實現降維打擊，迅速崛起。這個金手指的設定，能夠讓讀者對主角如何利用這種能力解決困境、顛覆舊秩序產生強烈的期待感。"])
    special_abilities: Optional[List[SpecialAbility]] = Field(None, description="主要金手指信息。金手指可以是各種系統、模擬器等這種具體的，也可以是某種優勢/天賦/體質等，例如主角重生或者穿越，那麼ta的先知先覺也是一種金手指。")


class OneSentence(BaseModel):
    """1: 根據tags、金手指設計一句話概述的請求模型"""
    one_sentence_thinking: str = Field(description="從標籤/金手指到一句話概述的創作思考過程。",examples=["示例輸出，僅供學習思考方式，不要被具體內容影響：考慮到'玄幻奇幻-異世大陸'的主題和'穿越'、'異界科學流'等標籤，我首先需要構建一個跨世界的故事框架。現代劍道高手與異世界魔法師的相遇是個很好的切入點，'禁忌魔法傳送門'金手指爲這一相遇提供了合理契機。同時，'單CP'的情感標籤要求這段關係要成爲故事的重要線索。'文明碰撞'和'異界科學流'標籤則提示要讓主角帶來現代世界的知識優勢，形成獨特的衝突和看點。綜合這些元素，我決定構建一個關於現代人進入魔法世界，通過知識優勢與個人成長影響整個異界命運的故事。"])
    one_sentence: str = Field(description="一句話概述整本小說內容")


class ParagraphOverview(BaseModel):
    """2: 根據一句話概述等信息擴充爲一段話概述的請求模型"""
    overview_thinking: str = Field(description="從一句話概述到一段話大綱的創作思考過程。",examples=["示例輸出，僅供學習思考方式，不要被具體內容影響：基於一句話概述，進一步思考故事的具體展開。從'穿越'標籤出發，需要交代主角穿越後的身份轉變和初始困境。'反派流'和'幕後流'決定了主角必須採取非傳統的反派手段。'種田流'提示要詳細描寫魔族社會發展過程。'傲慢天賦'金手指則提供了主角解決問題的獨特方式。整個故事需要展現出主角如何利用現代思維和智謀，在有限時間內完成魔族改造和人類世界的和平滲透。"])
    overview: str = Field(description="擴展後的小說大綱")
    

class SocialSystem(BaseModel):
    power_structure: str = Field(description="權力架構（如：封建王朝/資本聯邦）")
    currency_system: List[str] = Field(description="貨幣體系")
    background:List[str]=Field(description="該社會體系的勢力格局背景、歷史傳說等")
    major_power_camps: List[OrganizationCard] = Field(description="主要組織/門派/勢力陣營，僅在此生成跨卷長期影響的核心組織。")
    civilization_level: Optional[str] = Field(description="科技/文明發展水平")

class CoreSystem(BaseModel):
    system_type: str = Field(min_length=1,description="體系類型（力量/社會/科技/異能等）")
    name: str = Field(description="體系名稱（如：鬥氣/資本規則/朝堂權謀）")
    levels: Optional[List[str]] = Field(None, description="等級/階層劃分（可選）")
    source: str = Field(description="能量/權力來源（如：靈氣/資本/皇權）")

class SettingItem(BaseModel):
    title: str = Field(description="設定標題，例如：地理宇宙觀、歷史傳說、種族設定等")
    description: str = Field(description="該項設定的具體描述")

class WorldviewTemplate(BaseModel):
    """
    世界觀模板
    """
    world_name: str = Field(min_length=2, description="世界名稱")
    core_conflict: str = Field(description="世界核心矛盾（如：資源爭奪/種族仇恨）")
    social_system: SocialSystem = Field(description="社會體系")
    power_systems: List[CoreSystem] = Field(description="核心體系列表，可包含力量/科技/異能等多種體系，避免設定過於複雜，最多設置兩種體系。若是現實/歷史等寫實題材，則可置爲空",max_length=2)
    # key_settings: Optional[List[SettingItem]] = Field(description="其他關鍵世界觀設定（可選）")

class WorldBuilding(BaseModel):
    world_view_thinking: str = Field(description="世界觀設計的思考過程",examples=["示例輸出，僅用於學習思考方式，不要被具體內容影響：在設計世界觀時，我希望構建一個既貼近現實又充滿科幻想象力的框架。首先，爲了讓讀者有代入感，我選擇將故事背景設定在現代都市，這樣主角的特殊能力與日常生活的衝突會更具張力。但僅僅是現代都市顯然不夠支撐“時空穿越”的主題，因此，我引入了“夢境”作爲連接現實與未來的橋樑。這個夢境世界，最初是現實的映射，但隨着主角的幹預，它會發生劇烈變化，甚至出現“舊海”和“新海市”這種未來世界的差異，這爲世界觀增添了層次感和探索空間。爲了解釋這種變化，我需要一套嚴謹的時空法則，比如“時空蝴蝶效應”、“歷史線修正”等，這些法則不僅解釋了夢境與現實的互動，也爲劇情的推進和衝突的產生提供了邏輯基礎。同時，爲了承載“文明推演”和“異界科學流”的標籤，我構思了一個隱藏在幕後的組織，他們掌握着超越時代的科技和對時空法則的深刻理解，他們的存在是世界核心矛盾的體現——即關於歷史走向的掌控權。社會體繫上，現實世界是現代社會，而未來夢境則可能呈現出科技高度發達但社會畸形（如積分至上）或末日廢土（如輻射災害）的多種面貌，這種對比能增強故事的深度和警示意義。核心驅動體繫上，除了主角的夢境能力，還需要有“超時空粒子”等科學概念作爲力量來源和理論支撐，使得整個世界觀在科幻的框架下顯得自洽且充滿探索潛力。"])
    world_view: WorldviewTemplate


# === Step 3: Blueprint Schemas ===


class Blueprint(BaseModel):
    volume_count: int = Field(description="預期小說的分卷數,通常設置爲3~6卷")
    character_thinking: str = Field(description="角色設計思考過程",examples=["示例輸出，僅供學習思考方式，不要被具體內容影響：在設計角色時，我秉持着“多樣性與互補性”的原則，確保每個核心角色都能在故事中發揮獨特的作用，並與主角團形成緊密的聯繫。\n\n首先是主角王小明。他作爲“穿越者”，必須具備現代人的思維和適應能力。我設定他是一名劍道高手，這既能讓他快速融入異世界，又能與異世界的“劍術”體系相呼應。他的核心驅動力是“高額酬金”和“守護海雯”，這讓他從一個旁觀者逐漸轉變爲異世界的參與者和守護者。他的成長弧光將是“從現實世界的普通人到異世界的救世主”，這與“進化流”的標籤緊密相連。\n\n女主角海雯是故事的引路人。她必須是異世界的核心人物，擁有強大的魔法天賦和獨特的背景。我設定她是“天才魔法師”和“王族聯姻的逃犯”，這爲她提供了最初的困境和行動動機。她與主角的“閃婚”設定，迅速確立了他們的CP關係，也爲後續的情感發展奠定了基礎。她的核心驅動力是“逃避聯姻”和“拯救世界”，這讓她在個人命運與世界命運之間找到了平衡點。她的角色弧光是“從逃亡者到拯救世界的王宮魔法師”，展現了她的成長與擔當。\n\n希斯作爲主要反派，必須強大且神祕。我設定她是“海雯的姑姑”和“邪惡魔法師”，這種親緣關係增加了故事的複雜性和情感張力。她的核心動機是“毀滅世界”，這與失落文明的詛咒緊密相關。她的角色弧光是“從天才魔法師到毀滅者，最終選擇離開”，爲故事的結局增添了悲劇色彩。\n\n林曉雪則作爲連接現實世界的橋樑，她的“學霸”設定讓她能夠爲異世界提供現代知識，體現“異界科學流”和“文明碰撞”的標籤。\n\n通過這些角色的設計，我希望構建一個充滿張力、情感豐富、並能共同推動宏大敘事的角色羣像。"])
    character_cards: List[CharacterCard] = Field(description="核心角色卡片列表，僅在此生成跨卷長期影響的核心角色")
    
    # organization_thinking:str=Field(description="組織/勢力/陣營設計思考過程，注意與scene區分")
    # organization_cards: List[OrganizationCard] = Field(description="核心組織/勢力/陣營卡片列表，僅在此生成跨卷長期影響的核心組織。注意與scene_cards區分")
    
    scene_thinking: str = Field(description="場景設計思考過程",examples=["示例輸出，僅供學習思考方式，不要被具體內容影響：在設計地圖和場景時，我遵循了從局部到全局、從已知到未知、層層遞進的原則，以確保故事的節奏感和世界觀的逐步展開。我的核心思路是：每個場景不僅是故事發生的地點，更是推動劇情、展現角色成長、揭示世界觀祕密的關鍵。\n\n**第一卷：初入異世與初步探索**\n我首先設置了藍星（現實世界）作爲故事的起點和主角的“已知世界”，這讓讀者有代入感。然後通過“墨蘭塔”和“蘭特王國(明月城)”引入異世界的核心地域，這裏是魔法與劍並存的典型場景，也是初期衝突的爆發點。墨蘭塔作爲魔法師的聖地，既是海雯的背景，也爲主角學習魔法提供了場所。明月城則代表了異世界的政治中心和戰爭前線。這些場景的作用是讓主角初步適應異世界，展現其適應能力和初步實力提升，並引出主要勢力。\n\n**第二卷：勢力發展與聯盟建立**\n隨着劇情發展，我需要更廣闊的舞臺來展現主角團的勢力擴張和宏大計劃。因此，引入“蘭特王國（驚鴻之城）”作爲新的盟友基地，這裏將成爲公主復國和建立同盟的戰略中心。同時，爲了展現戰爭的全面性，我設計了“高欄聯邦（臨崖城/中部哨塔/日出山）”作爲重要的戰場和政治博弈地，通過這裏的衝突來推動聯盟的形成。解放“明月城”則是這一卷的高潮，標誌着復國計劃的關鍵一步。這些場景的作用是讓主角團從被動應戰轉變爲主動出擊，展現其戰略眼光和領導力，並促成同盟的建立。\n\n**第三卷：統一戰爭與古老祕密的揭示**\n進入第三卷，故事重心轉向統一異世界大陸和揭示更深層次的祕密。因此，我將場景擴展到“日月國”和“聖瓦倫帝國（特西斯丁堡）”。日月國是聯軍推進的必經之地，通過這裏的戰役展現主角團的強大力量。聖瓦倫帝國首都“特西斯丁堡”是最終決戰的地點，它的陷落標誌着舊秩序的終結。這些場景的作用是完成統一大業，同時揭示世界觀的深層祕密，爲最終的危機埋下伏筆。\n\n**第四卷：末日危機與最終抉擇**\n最後一卷，世界面臨毀滅，場景設計圍繞“拯救”和“終結”展開。“臨崖城”和“驚鴻之城”再次出現，但這次它們承載的是收集王族之血和科技求生的希望。最終的“起源之地/燃燒的山巔”是決戰的舞臺，這裏是詛咒的源頭，也是解咒的關鍵。這些場景的作用是集中所有線索，完成最終的救贖，並讓主角團做出關於歸屬的最終選擇，爲整個故事畫上句號。"])
    scene_cards: List[SceneCard] = Field(description="主要地圖/場景/副本卡片列表，僅在此生成跨卷長期影響的核心地圖/場景。注意與organization_cards聯繫，例如某個地圖是某個組織/勢力的活動範圍則需要標明。")


# === Step 4: Volume Outline Schemas===

class CharacterAction(BaseModel):
    """角色卡，涵蓋了各種信息"""
    name: str = Field(description="角色名稱")
    description: str = Field(description="以第一視角講述該角色在這卷內的主要事蹟")

class StoryLine(BaseModel):
    """故事線信息"""
    story_type: Literal['主線', '輔線'] = Field(description="故事線類型")
    name: str = Field(description="用一個簡單的名稱表示該線")
    overview: str = Field(description="故事線內容概述，需要詳略得當，涉及到的所有場景、角色等元素都應在這個概述中體現到。")


class VolumeOutline(BaseModel):
    """
    分卷大綱的核心數據模型
    """
    volume_number: Optional[int] = Field(description="第幾卷")
    thinking: Optional[str] = Field(description="根據提供的世界觀、人物、地圖/副本,思考本卷要如何展開,需要設計什麼主線/輔線?如何推動劇情發展?",examples=["示例輸出，僅供學習思考方式，不要被具體內容影響：本卷作爲開篇，我的核心思考是如何迅速確立主角“無限復活”的金手指特性，並將其與殘酷的異世大陸背景相結合，製造強烈的生存壓迫感，從而驅動主角從絕境中崛起。我需要設計一個循序漸進的成長路徑，讓主角從一個瀕死之人，通過每次復活積累經驗和知識，逐步適應環境，並最終在A市站穩腳跟，積累原始資本，建立初步勢力。同時，爲了後續的宏大敘事，我必須在這一卷中埋下世界觀的伏筆，例如社會階層的固化、更高文明的操控等，通過主角的視角逐步揭示。在人物塑造上，我將引入一羣性格各異的夥伴，他們既是主角的助力，也能通過他們的視角反襯主角的強大和特殊。爽點方面，主角利用金手指的“先知”優勢，在股市和冒險中實現降維打擊，以及最終對早期反派的復仇，都將是重要的爽點設計。"])
    main_target: StoryLine = Field(description="根據thinking設計主線目標,要讓主角發展到什麼地步?需描述準確數據")
    branch_line: Optional[List[StoryLine]] = Field(description="該卷的輔線或支線,包含1~3條核心輔線")
    character_thinking: Optional[str] = Field(description="結合overview、提供的角色信息,如性格、核心驅動力、角色弧光等,思考在該卷要驅動角色實體們做什麼事?要讓哪些角色出場?是否要引入輔助角色?",examples=["示例輸出，僅學習思考方式，不要被具體內容影響：在本卷中，我將重點驅動主角，讓他充分利用“無限復活”的能力，從一個絕境中的倖存者，逐步成長爲A市的領袖。他將通過反覆試錯來學習戰鬥技巧、社會規則，並利用信息差在股市中快速積累財富。我還需要引入孫清雨、王火、韓天等核心配角，讓他們在主角的成長過程中扮演重要的輔助角色：孫清雨作爲主角的第一個夥伴和忠實追隨者，將見證並參與主角的早期崛起；王火則提供技術支持，併成爲主角“復活”祕密的知情人；韓天則在裝備改造和技術研發上提供關鍵幫助。這些角色的出場和互動，不僅能推動劇情發展，也能豐富主角的人設，展現他智謀超羣、善於利用資源的特點。同時，林森作爲本卷的主要反派，將是主角初期反抗舊秩序的具象化目標，他的存在將不斷刺激主角變強和復仇。"])
    new_character_cards: Optional[List[CharacterCard]] = Field(default=None, description="如有新增關鍵角色，在此補充其信息，life_span爲短期。非必要儘量不引入新角色")
    new_scene_cards: Optional[List[SceneCard]]= Field(default=None, description="如有新增關鍵場景/地圖/副本，在此補充其信息，life_span爲短期，非必要儘量不引入新場景")
    # stage_lines: Optional[List[StageLine]] = Field(default=[], description="設計該卷的詳細故事脈絡，按階段來劃分，注意切分故事階段時詳略得當，每個階段章節跨度不要太大,最好不超過30章")
    stage_count:int=Field(description="預期該卷的階段劇情，將該卷的劇情分爲n個階段來敘述，通常爲4~6個")
    character_action_list: Optional[List[CharacterAction]] = Field( description="根據卷內設計，概述關鍵角色實體的行動與變化")
    entity_snapshot: Optional[List[str]] = Field(description="卷末時，關鍵實體（角色爲主）快照狀態信息，，包括等級/修爲境界、財富、功法等準確信息，以便收束劇情")

class WritingGuide(BaseModel):
    """
    寫作指南，用於指導AI在特定卷中創作時需要注意的細節。
    """
    volume_number: int = Field(description="該寫作指南對應的卷號")
    content: str = Field(description="AI根據方法論生成的、用於指導本卷寫作的具體內容。字數控制在1000字以內。",min_length=100)


class ReviewResultCardContent(BaseModel):
    review_target_card_id: int = Field(description="被審核卡片 ID")
    review_target_title: str = Field(description="被審核卡片標題")
    review_target_type: Literal['card'] = Field(default='card', description="被審核目標類型")
    review_type: Literal['chapter', 'stage', 'card', 'custom'] = Field(description="審核類型")
    review_profile: str = Field(description="審核 profile code")
    review_target_field: Optional[str] = Field(default=None, description="被審核字段路徑")
    quality_gate: Literal['pass', 'revise', 'block'] = Field(description="審核結論")
    review_markdown: str = Field(description="審核結果正文，使用 markdown 格式")
    prompt_name: str = Field(description="審核所使用的提示詞名稱")
    llm_config_id: Optional[int] = Field(default=None, description="審核使用的模型配置")
    reviewed_at: str = Field(description="審核時間（ISO 字符串）")
    target_snapshot: Optional[str] = Field(default=None, description="被審核內容快照")
    meta: Optional[dict[str, Any]] = Field(default_factory=dict, description="擴展元數據")

class ChapterOutline(BaseModel):
    """章節大綱"""
    volume_number: int = Field(description="卷號，如果沒有找到，則設置爲0")
    stage_number:int=Field(description="該章節屬於第幾個階段，從1開始")
    title: str= Field(description="章節標題")
    chapter_number: int = Field(description="章節序號")
    
    overview: str = Field(description="章節細綱,詳略得當，避免過於單薄。如果主角有了顯著的提升，則相關信息不能省略，需要準確數據描述出來(如實力大幅提升、經濟或資源大幅增長了多少)。",min_length=100)
    entity_list: List[str] = Field(
        description="章節中出場的重要實體列表，只能從上下文提供的組織/角色/場景卡實體中選擇，不得新增、自創；實體名稱必須是純名稱（不得包含括號/備註）。注意,爲了精簡上下文，避免實體列表中出現該章節未出場的冗餘實體",
    )

    

class StageLine(BaseModel):
    """故事按階段劃分的信息"""
    volume_number:int=Field(description="該故事階段屬於第幾卷")
    stage_number:int=Field(description="該故事階段是第幾個階段，從1開始")
    stage_name: str = Field(description="用一個名稱或一句話簡單概述這個階段")
    reference_chapter: Tuple[int, int] = Field(description="該部分劇情的起始和結束章節號,跨度通常爲10~20章左右")
    analysis: Optional[str] = Field(description="以一個經驗豐富的網文寫手代入作者第一人稱視角,'我'是如何思考設置這部分的劇情的,該部分劇情對於分卷的主線/輔線起到什麼作用?該階段劇情的爽點是什麼？末尾是否設置鉤子/懸念？")
    overview: Optional[str] = Field(description="這個階段劇情內容具體概述，需要詳略得當，涉及到的主要實體，如角色、場景/地圖、組織等元素都應在這個概述中體現到。另外，若主角有了顯著提升（如提升了主角多少實力或地位、增長了主角多少財富或資源之類的），則相關信息需要準確數據描述，不能省略")
    chapter_outline_list:Optional[List[ChapterOutline]]=Field(description="根據reference_chapter、overview生成所需的章節大綱。注意章節大綱的標題不要包含”第x章這種前綴")
    entity_snapshot: Optional[List[str]] = Field(description="階段末時，關鍵實體（角色爲主）快照狀態信息，包括等級/修爲境界、財富、功法等準確信息，以便收束劇情，確保最後一個階段時，劇情發展能夠使得實體狀態收束到該卷末的實體狀態。")
    @model_validator(mode="after")
    def validate_chapter_outline_coverage(self):
        # Allow empty list for workflow post-processing cleanup.
        if not self.chapter_outline_list:
            return self

        start, end = self.reference_chapter
        if start > end:
            raise ValueError("reference_chapter start must be <= end")

        actual_numbers = [item.chapter_number for item in self.chapter_outline_list]
        expected_numbers = list(range(start, end + 1))
        if actual_numbers != expected_numbers:
            raise ValueError(
                "chapter_outline_list.chapter_number must be contiguous and fully cover reference_chapter"
            )
        return self


# === Step 6: Batch Chapter Outline Schemas===

class Chapter(BaseModel):
    volume_number: int = Field( description="卷號，如果沒有找到，則設置爲0")
    stage_number: int=Field(description="該章節屬於第幾個階段，從1開始")
    title: str = Field(description="章節標題")
    chapter_number: int = Field(description="章節序號")

    entity_list: List[str] = Field(
        description="章節中參與的重要實體列表，只能從提供的實體中選擇；name 必須是純名稱（不得包含括號/備註）",
    )
    content:Optional[str]=Field(default="",description="章節正文內容")
    

