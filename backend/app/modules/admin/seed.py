"""配置域种子：尺寸预设与 8 个系统提示词（幂等）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import SizePreset, SystemPrompt

# (平台名称, 宽, 高, 排序)
SIZE_PRESETS: list[tuple[str, int, int, int]] = [
    ("淘宝/天猫", 1000, 1000, 0),
    ("京东", 1000, 1000, 1),
    ("拼多多", 1000, 1000, 2),
    ("抖音", 1000, 1000, 3),
]

# (agent_code, 名称, 默认提示词)
AGENTS: list[tuple[str, str, str]] = [
    ("planner", "规划 Agent", "你是电商图的规划 Agent，负责拆解用户需求为 1 张主图 + 5 张详情图的生成计划。"),
    ("product_understanding", "商品理解 Agent", "你是商品理解 Agent，负责从商品名称与上传图推断类目、卖点、人群与场景。"),
    ("copywriter", "文案 Agent", "你是文案 Agent，负责为商品图生成标题、卖点与说明文案。"),
    ("prompt_builder", "提示词 Agent", "你是提示词 Agent，负责把文案与风格转换为结构化的生图提示词并预留文字区。"),
    ("image_generator", "生图执行 Agent", "你是生图执行 Agent，负责调用图像模型完成图生图/文生图。"),
    ("quality_reviewer", "质量审核 Agent", "你是质量审核 Agent，负责检查文字错乱、主体变形与合规问题。"),
    ("repairer", "修复 Agent", "你是修复 Agent，负责根据审核问题修正提示词并触发重新生成。"),
    ("platform_rule", "平台规范 Agent", "你是平台规范 Agent，负责校验尺寸、违禁词与类目规则。"),
]


def seed_config(db: Session) -> None:
    """幂等写入尺寸预设与系统提示词。"""
    for platform_name, width, height, sort_order in SIZE_PRESETS:
        existing = db.scalar(
            select(SizePreset).where(
                SizePreset.platform_name == platform_name,
                SizePreset.width == width,
                SizePreset.height == height,
            )
        )
        if existing is None:
            db.add(
                SizePreset(
                    platform_name=platform_name,
                    width=width,
                    height=height,
                    sort_order=sort_order,
                )
            )
            print(f"[种子] 新增尺寸预设 {platform_name} {width}x{height}")

    for agent_code, name, content in AGENTS:
        existing = db.scalar(select(SystemPrompt).where(SystemPrompt.agent_code == agent_code))
        if existing is None:
            db.add(
                SystemPrompt(
                    agent_code=agent_code,
                    name=name,
                    content=content,
                    current_version=1,
                )
            )
            print(f"[种子] 新增系统提示词 {agent_code}")

    db.commit()
