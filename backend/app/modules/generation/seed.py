"""生图任务演示种子：8 条提示词、1 条模型配置、模板/素材/尺寸。

幂等：已存在的数据跳过，不覆盖后台可能做过的修改。
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import storage
from app.models.config import (
    MaterialAsset,
    ModelConfig,
    PromptVersion,
    SizePreset,
    SystemPrompt,
    Template,
)
from app.modules.generation import config_service

PROMPT_REVISION_MARKERS = {
    "quality_reviewer": "不单独导致 passed=false",
    "prompt_builder": "默认不出现真人正脸",
}

SYSTEM_PROMPTS: dict[str, tuple[str, str]] = {
    "planner": (
        "规划 Agent",
        """你是电商 AIGC 规划 Agent。根据商品参数快照、需求摘要、最近聊天摘要与模板信息，规划一整套 6 张图。
要求：
1. images 固定 6 项，index 依次为 1~6；第 1 张 role=main，其余 5 张 role=detail。
2. 每张 theme 必须具体、符合电商场景，且 6 张主题互不重复。
3. copy_focus 说明该张文案重点；layout_hint 说明版式建议。
4. order 固定为 ["product_understanding","copywriter","prompt_builder","image_generator"]。
只输出 JSON，不要输出解释或 Markdown。结构：
{"image_count":6,"images":[{"index":1,"role":"main","theme":"","copy_focus":"","layout_hint":""}],"order":["product_understanding","copywriter","prompt_builder","image_generator"]}""",
    ),
    "product_understanding": (
        "商品理解 Agent",
        """你是商品理解 Agent。根据商品名称、上传商品图、需求摘要、聊天摘要与素材候选，输出商品画像。
要求：
1. category、target_audience 为非空中文；selling_points 3~5 条；scenes、constraints 为数组。
2. material_ids 只能从 material_candidates 的 material_id 中选择，最多 3 个；没有合适素材时返回空数组。
3. 未上传商品图时，在 constraints 中明确写“无实物参考”。
只输出 JSON，不要输出解释或 Markdown。结构：
{"category":"","selling_points":[""],"target_audience":"","scenes":[""],"constraints":[""],"material_ids":[]}""",
    ),
    "copywriter": (
        "文案 Agent",
        """你是电商文案 Agent。根据商品画像、6 张图计划、风格与模板信息，为每张图输出文案块。
要求：
1. 全部使用简体中文；标题 6~12 字；卖点 3 条，每条 4~10 字；body 一句话；tone 说明语气。
2. 不生成价格、促销倒计时、销量等用户未提供的信息。
3. images 固定 6 项，index 为 1~6。
只输出 JSON，不要输出解释或 Markdown。结构：
{"images":[{"index":1,"title":"","selling_points":[""],"body":"","tone":""}]}""",
    ),
    "prompt_builder": (
        "提示词 Agent",
        """你是生图提示词 Agent。根据文案块、商品画像、风格、尺寸、模板与素材候选，为 6 张图输出生图提示词。
要求：
1. prompt 只描述画面、光线、构图与风格，必须显式要求“上方标题区留白、下方卖点区留白”。
2. 不要把大段中文文案写进 prompt，避免模型直接画字。
3. whitespace 给出 top_ratio 与 bottom_ratio（0~0.5）。
4. reference_asset_ids 只能使用素材候选中的 material_id。
5. model_params 的 width/height 使用给定尺寸。
6. 默认不出现真人正脸；优先平铺/挂拍/局部特写，除非用户明确要求模特上身。
7. images 固定 6 项，index 为 1~6。
只输出 JSON，不要输出解释或 Markdown。结构：
{"images":[{"index":1,"prompt":"","negative_prompt":"","whitespace":{"top_ratio":0.18,"bottom_ratio":0.22},"reference_asset_ids":[],"model_params":{"width":1000,"height":1000}}]}""",
    ),
    "image_generator": (
        "生图执行 Agent",
        """你是生图执行 Agent 的系统约束说明。调用 Seedream 时：
1. 只负责画面，不负责写中文；提示词必须留出文字区。
2. 有上传商品图时以商品图为主参考，保持商品外观、颜色、结构一致。
3. 单张超时 120 秒；失败最多尝试 2 次。""",
    ),
    "quality_reviewer": (
        "质量审核 Agent",
        """你是电商图片质量审核 Agent。检查生成图是否存在：商品变形、主体缺失、严重违规。
留白区是否可用只作为 issues 提示，不单独导致 passed=false（后端会在文字合成阶段加半透明底兜底）。
只有商品主体变形/缺失/严重违规才判 passed=false。
只输出 JSON，不要输出解释或 Markdown。结构：
{"passed":true,"issues":[],"checks":{"product_fidelity":"pass","deformity":"pass","whitespace_available":"pass","compliance":"pass"}}
任何硬性项不通过时 passed=false，并在 issues 中用中文说明具体问题。""",
    ),
    "repairer": (
        "修复 Agent",
        """你是提示词修复 Agent。根据审核问题、原提示词与商品画像，修正提示词，最多修复一次。
要求：
1. 保持商品主体不变形，修复审核指出的问题。
2. 继续显式保留上方标题区与下方卖点区。
只输出单张图的 JSON，不要输出解释或 Markdown。结构：
{"index":1,"prompt":"","negative_prompt":"","whitespace":{"top_ratio":0.18,"bottom_ratio":0.22},"reference_asset_ids":[]}""",
    ),
    "platform_rule": (
        "平台规范 Agent",
        """你是电商平台规范审核 Agent。依据以下平台规则检查文案与尺寸：
{{platform_rules}}
只输出 JSON，不要输出解释或 Markdown。结构：
{"passed":true,"issues":[],"checks":{"size":"pass","prohibited_words":"pass","category_rules":"pass"}}
任何一项不通过时 passed=false，并在 issues 中用中文说明具体问题。""",
    ),
}

TEMPLATE_SEEDS = [
    {
        "name": "简约白底",
        "style_text": "简洁白底，柔和棚拍光",
        "prompt_template": "浅色背景，商品居中，柔和棚拍光，干净留白",
        "layout_ref": "标题上方居中，卖点下方居中",
        "sort_order": 0,
        "slug": "minimal-white",
    },
    {
        "name": "暖调生活",
        "style_text": "暖色生活场景，自然光",
        "prompt_template": "暖色生活场景，自然光，商品与场景融合，保留文字区",
        "layout_ref": "标题上方居中，卖点下方居中",
        "sort_order": 1,
        "slug": "warm-life",
    },
]

MATERIAL_SEEDS = [
    {
        "name": "室内白墙",
        "tags": ["服饰", "室内"],
        "style_tags": ["简约", "白底"],
        "sort_order": 0,
        "slug": "indoor-white",
        "color": (235, 240, 245),
    },
    {
        "name": "木质桌面",
        "tags": ["服饰", "室内"],
        "style_tags": ["生活", "暖调"],
        "sort_order": 1,
        "slug": "wood-table",
        "color": (196, 160, 120),
    },
    {
        "name": "城市街景",
        "tags": ["服饰", "户外"],
        "style_tags": ["通勤", "自然光"],
        "sort_order": 2,
        "slug": "city-street",
        "color": (150, 170, 190),
    },
    {
        "name": "纯色背景",
        "tags": ["数码", "白底"],
        "style_tags": ["简约", "棚拍"],
        "sort_order": 3,
        "slug": "solid-bg",
        "color": (245, 245, 245),
    },
]

SIZE_SEEDS = [
    ("淘宝/天猫", 1000, 1000, 0),
    ("京东", 1000, 1000, 1),
    ("拼多多", 1000, 1000, 2),
    ("抖音", 1000, 1000, 3),
]


def _placeholder_image(color: tuple[int, int, int], size: int) -> bytes:
    image = Image.new("RGB", (size, size), color)
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 20,
        outline=(255, 255, 255),
        width=max(2, size // 100),
    )
    draw.ellipse(
        [size // 3, size // 3, size * 2 // 3, size * 2 // 3],
        fill=(255, 255, 255),
    )
    buffer = BytesIO()
    image.save(buffer, format="WEBP", quality=85)
    return buffer.getvalue()


def _placeholder_material(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (600, 600), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 420, 600, 600], fill=(220, 220, 220))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _ensure_prompts(db: Session) -> None:
    for agent_code, (name, content) in SYSTEM_PROMPTS.items():
        existing = db.scalar(
            select(SystemPrompt).where(SystemPrompt.agent_code == agent_code)
        )
        if existing is not None:
            # 10/6 号种子写入的是简短占位提示词；首次接入 4 号时升级为可直接驱动
            # 真实模型的详细提示词。已由后台编辑过的长提示词不覆盖。
            if len((existing.content or "").strip()) < 80:
                existing.name = name
                existing.content = content
                existing.current_version = (existing.current_version or 1) + 1
                db.add(
                    PromptVersion(
                        prompt_id=existing.id,
                        agent_code=agent_code,
                        version=existing.current_version,
                        content=content,
                    )
                )
                print(f"[种子] 升级系统提示词 {agent_code} 至 v{existing.current_version}")
            else:
                marker = PROMPT_REVISION_MARKERS.get(agent_code)
                if marker and marker not in (existing.content or ""):
                    existing.content = content
                    existing.current_version = (existing.current_version or 1) + 1
                    db.add(
                        PromptVersion(
                            prompt_id=existing.id,
                            agent_code=agent_code,
                            version=existing.current_version,
                            content=content,
                        )
                    )
                    print(
                        f"[种子] 定向升级系统提示词 {agent_code} 至 v{existing.current_version}"
                    )
            continue
        prompt = SystemPrompt(
            agent_code=agent_code,
            name=name,
            content=content,
            current_version=1,
            is_active=True,
        )
        db.add(prompt)
        db.flush()
        db.add(
            PromptVersion(
                prompt_id=prompt.id,
                agent_code=agent_code,
                version=1,
                content=content,
            )
        )
        print(f"[种子] 新建系统提示词 {agent_code}")


def _ensure_model_config(db: Session) -> None:
    existing = db.scalar(
        select(ModelConfig).where(ModelConfig.is_active.is_(True)).limit(1)
    )
    if existing is not None:
        # 10/6 号种子可能写入 demo 模型名；首次接入 4 号时同步为真实模型名。
        changed = False
        if not existing.base_url:
            existing.base_url = settings.DOUBAO_BASE_URL
            changed = True
        if not existing.text_model or "demo" in existing.text_model:
            existing.text_model = settings.DOUBAO_TEXT_MODEL
            changed = True
        if not existing.image_model or "demo" in existing.image_model:
            existing.image_model = settings.DOUBAO_IMAGE_MODEL
            changed = True
        if not existing.vision_model or "demo" in existing.vision_model:
            existing.vision_model = settings.DOUBAO_VISION_MODEL or None
            changed = True
        if changed:
            print("[种子] 同步模型配置为真实模型名")
        return
    db.add(
        ModelConfig(
            provider="volcengine_ark",
            base_url=settings.DOUBAO_BASE_URL,
            api_key_ciphertext=None,
            text_model=settings.DOUBAO_TEXT_MODEL,
            image_model=settings.DOUBAO_IMAGE_MODEL,
            vision_model=settings.DOUBAO_VISION_MODEL or None,
            temperature=0.7,
            timeout_seconds=120,
            concurrency=4,
            retry_count=1,
            is_active=True,
        )
    )
    print("[种子] 新建启用的模型配置")


def _ensure_templates(db: Session) -> None:
    for item in TEMPLATE_SEEDS:
        existing = db.scalar(select(Template).where(Template.name == item["name"]))
        path = f"templates/seed/{item['slug']}.webp"
        if existing is not None:
            if not storage.exists(existing.thumbnail_path):
                storage.save(existing.thumbnail_path, _placeholder_image((232, 238, 246), 400))
            continue
        storage.save(path, _placeholder_image((232, 238, 246), 400))
        db.add(
            Template(
                name=item["name"],
                style_text=item["style_text"],
                thumbnail_path=path,
                prompt_template=item["prompt_template"],
                layout_ref=item["layout_ref"],
                sort_order=item["sort_order"],
                status="active",
            )
        )
        print(f"[种子] 新建模板 {item['name']}")


def _ensure_materials(db: Session) -> None:
    for item in MATERIAL_SEEDS:
        existing = db.scalar(
            select(MaterialAsset).where(MaterialAsset.name == item["name"])
        )
        path = f"materials/seed/{item['slug']}.png"
        if existing is not None:
            if not storage.exists(existing.file_path):
                storage.save(existing.file_path, _placeholder_material(item["color"]))
            continue
        storage.save(path, _placeholder_material(item["color"]))
        db.add(
            MaterialAsset(
                name=item["name"],
                file_path=path,
                thumbnail_path=None,
                tags=item["tags"],
                style_tags=item["style_tags"],
                sort_order=item["sort_order"],
                status="active",
            )
        )
        print(f"[种子] 新建素材 {item['name']}")


def _ensure_sizes(db: Session) -> None:
    for platform_name, width, height, sort_order in SIZE_SEEDS:
        existing = db.scalar(
            select(SizePreset).where(
                SizePreset.platform_name == platform_name,
                SizePreset.width == width,
                SizePreset.height == height,
            )
        )
        if existing is not None:
            continue
        db.add(
            SizePreset(
                platform_name=platform_name,
                width=width,
                height=height,
                sort_order=sort_order,
                status="active",
            )
        )
        print(f"[种子] 新建尺寸预设 {platform_name} {width}x{height}")


def seed_generation_config(db: Session) -> None:
    """写入生图任务演示配置；重复执行不产生重复数据。"""
    _ensure_prompts(db)
    _ensure_model_config(db)
    _ensure_templates(db)
    _ensure_materials(db)
    _ensure_sizes(db)
    db.commit()
    config_service.refresh()
