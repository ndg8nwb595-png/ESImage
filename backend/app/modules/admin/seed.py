"""配置域种子：尺寸预设与 8 个系统提示词（幂等）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import ModelConfig, PromptVersion, SizePreset, SystemPrompt
from app.models.user import User

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
    # 版本 1 的修改人记为演示超管；账号不存在时允许为空
    seed_user = db.scalar(select(User).where(User.username == "demo_super"))
    seed_user_id = seed_user.id if seed_user is not None else None

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
            existing = SystemPrompt(
                agent_code=agent_code,
                name=name,
                content=content,
                current_version=1,
            )
            db.add(existing)
            db.flush()
            print(f"[种子] 新增系统提示词 {agent_code}")

        # 8 号要求每个 Agent 都有版本 1，缺失时补写，不覆盖已有内容。
        # 仅当当前版本仍为 1 时才可安全认定当前内容就是初版；
        # 若已被修改过且初版缺失，不伪造历史，交由人工处理。
        version_one = db.scalar(
            select(PromptVersion).where(
                PromptVersion.prompt_id == existing.id,
                PromptVersion.version == 1,
            )
        )
        if version_one is None:
            if existing.current_version <= 1:
                db.add(
                    PromptVersion(
                        prompt_id=existing.id,
                        agent_code=agent_code,
                        version=1,
                        content=existing.content,
                        created_by=seed_user_id,
                    )
                )
                print(f"[种子] 新增系统提示词版本 {agent_code} v1")
            else:
                print(
                    f"[种子] 警告：{agent_code} 当前版本 {existing.current_version} "
                    "缺少版本 1，跳过补写以避免伪造历史"
                )

    # 8 号模型配置：没有启用行时插入演示默认值
    active_config = db.scalar(select(ModelConfig).where(ModelConfig.is_active.is_(True)))
    if active_config is None:
        db.add(
            ModelConfig(
                provider="volcengine_ark",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key_ciphertext=None,
                text_model="doubao-seed-character-demo",
                image_model="doubao-seedream-demo",
                vision_model=None,
                temperature=0.7,
                timeout_seconds=120,
                concurrency=4,
                retry_count=1,
                max_context_tokens=32000,
                is_active=True,
            )
        )
        print("[种子] 新增模型配置（演示默认值）")

    db.commit()
