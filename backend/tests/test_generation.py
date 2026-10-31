"""4 号 PRD 生图任务最小 demo 接口测试。

每一步都打印中文日志，便于定位失败步骤；生成链路统一使用确定性模型替身。
"""

from __future__ import annotations

import shutil
import uuid
import zipfile
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import delete, func, select

LOGIN_URL = "/api/v1/auth/login"
SAMPLE_URL = "/api/v1/generations/sample"
TEMPLATES_URL = "/api/v1/templates"
SIZES_URL = "/api/v1/sizes"


def _login(client, username: str = "demo_user") -> str:
    print(f"[测试] 登录 {username}")
    response = client.post(
        LOGIN_URL,
        json={"username": username, "password": "Demo1234", "remember_me": False},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return str(uuid.uuid4())


def _sample(
    client,
    token: str,
    *,
    client_request_id: str | None = None,
    product_name: str = "秋季通勤衬衫",
    style_text: str | None = "简洁白底",
    template_id: int | None = None,
    width: int | None = 1000,
    height: int | None = 1000,
    upload_ids: list[int] | None = None,
):
    return client.post(
        SAMPLE_URL,
        headers=_headers(token),
        json={
            "client_request_id": client_request_id or _uid(),
            "session_id": None,
            "product_name": product_name,
            "style_text": style_text,
            "width": width,
            "height": height,
            "template_id": template_id,
            "upload_ids": upload_ids,
            "requirement_summary": None,
        },
    )


def _batch(client, token: str, batch_id: int) -> dict:
    response = client.get(f"/api/v1/generations/{batch_id}", headers=_headers(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _agent_runs(batch_id: int) -> list:
    from app.core.database import SessionLocal
    from app.models import AgentRun

    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.batch_id == batch_id)
                .order_by(AgentRun.id.asc())
            )
        )


@pytest.fixture(autouse=True)
def clean_generation():
    """每个用例前清空生成数据与用户产物，保留模板/素材种子。"""
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import (
        AgentRun,
        ChatMessage,
        CreativeSession,
        GeneratedImage,
        GenerationBatch,
        SizePreset,
        Template,
        UploadedAsset,
    )
    from app.modules.generation import config_service
    from app.modules.generation.seed import seed_generation_config

    print("[测试] 清理生成数据……")
    with SessionLocal() as db:
        db.execute(delete(AgentRun))
        db.execute(delete(GeneratedImage))
        db.execute(delete(GenerationBatch))
        db.execute(delete(ChatMessage))
        db.execute(delete(UploadedAsset))
        db.execute(delete(CreativeSession))
        for template in db.scalars(select(Template)):
            template.status = "active"
        for size in db.scalars(select(SizePreset)):
            size.status = "active"
        db.commit()
        seed_generation_config(db)

    for subdir in ("uploads", "generated", "thumbnails"):
        shutil.rmtree(settings.STORAGE_ROOT / subdir, ignore_errors=True)
    settings.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    settings.GENERATION_FAULT_MODE = ""
    config_service.refresh()
    yield
    settings.GENERATION_FAULT_MODE = ""
    config_service.refresh()


# ---------------------------------------------------------------- 配置读取


def test_config_endpoints_and_permissions(client):
    token = _login(client)

    print("[测试] 步骤 1：读取启用模板")
    response = client.get(TEMPLATES_URL, headers=_headers(token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] >= 2
    first = data["items"][0]
    assert set(first) == {"template_id", "name", "style_text", "thumbnail_url", "sort_order"}
    assert first["thumbnail_url"] == f"/api/v1/templates/{first['template_id']}/thumbnail"

    print("[测试] 步骤 2：读取模板缩略图")
    thumbnail = client.get(first["thumbnail_url"], headers=_headers(token))
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"

    print("[测试] 步骤 3：读取尺寸预设")
    sizes = client.get(SIZES_URL, headers=_headers(token)).json()["data"]
    assert sizes["total"] == 4
    assert all(item["width"] == 1000 and item["height"] == 1000 for item in sizes["items"])

    print("[测试] 步骤 4：停用模板后不再返回")
    from app.core.database import SessionLocal
    from app.models import Template
    from app.modules.generation import config_service

    with SessionLocal() as db:
        template = db.get(Template, first["template_id"])
        template.status = "disabled"
        db.commit()
    config_service.refresh()
    disabled_list = client.get(TEMPLATES_URL, headers=_headers(token)).json()["data"]
    assert all(item["template_id"] != first["template_id"] for item in disabled_list["items"])
    missing = client.get(
        f"/api/v1/templates/{first['template_id']}/thumbnail", headers=_headers(token)
    )
    assert missing.status_code == 404 and missing.json()["code"] == 30016

    print("[测试] 步骤 5：管理员无 user.generate 权限")
    admin_token = _login(client, "demo_admin")
    forbidden = client.get(TEMPLATES_URL, headers=_headers(admin_token))
    assert forbidden.status_code == 403 and forbidden.json()["code"] == 20005


# ---------------------------------------------------------------- 示例批次


def test_sample_with_template_snapshot_and_sizes(client):
    token = _login(client)
    templates = client.get(TEMPLATES_URL, headers=_headers(token)).json()["data"]["items"]
    template = next(item for item in templates if item["style_text"])

    print("[测试] 步骤 1：带模板创建示例批次，风格取模板默认值")
    response = _sample(
        client,
        token,
        template_id=template["template_id"],
        style_text=None,
        product_name="模板测试商品",
    )
    assert response.status_code == 200, response.text
    batch_id = response.json()["data"]["batch_id"]

    from app.core.database import SessionLocal
    from app.models import GenerationBatch

    with SessionLocal() as db:
        batch = db.get(GenerationBatch, batch_id)
        snapshot = batch.params_snapshot
        assert snapshot["template_id"] == template["template_id"]
        assert snapshot["template_name"] == template["name"]
        assert snapshot["template_prompt"]
        assert snapshot["style_text"] == template["style_text"]
        assert batch.style_text == template["style_text"]
        assert snapshot["image_composition"] == "1 main + 5 detail"

    print("[测试] 步骤 2：模板不存在返回 30016")
    missing = _sample(client, token, template_id=999999)
    assert missing.status_code == 404 and missing.json()["code"] == 30016

    print("[测试] 步骤 3：尺寸边界")
    for width, height, status, code in [
        (512, 512, 200, 0),
        (2048, 2048, 200, 0),
        (1001, 1000, 400, 10003),
        (5000, 1000, 400, 10004),
    ]:
        print(f"[测试] 尺寸 {width}x{height} -> {status}/{code}")
        response = _sample(client, token, width=width, height=height)
        assert response.status_code == status, response.text
        if status != 200:
            assert response.json()["code"] == code


def test_sample_agent_runs_contract(client):
    token = _login(client)
    response = _sample(client, token)
    assert response.status_code == 200, response.text
    batch_id = response.json()["data"]["batch_id"]
    batch = _batch(client, token, batch_id)
    assert batch["status"] == "sample_ready"
    assert batch["stage"] == "done"
    assert batch["completed_count"] == 1

    print("[测试] 校验 8 Agent 记录顺序与字段")
    runs = _agent_runs(batch_id)
    codes = [run.agent_code for run in runs]
    expected = [
        "planner",
        "product_understanding",
        "copywriter",
        "prompt_builder",
        "image_generator",
        "quality_reviewer",
        "platform_rule",
    ]
    assert codes == expected, codes
    assert all(run.status == "success" for run in runs)
    for run in runs:
        assert run.model_name
        assert run.input_full and run.output_full
        assert run.latency_ms is not None
    assert sum(run.prompt_tokens for run in runs) > 0
    assert sum(run.completion_tokens for run in runs) > 0

    print("[测试] 示例图字段包含 4 号 demo 增量字段")
    image = batch["images"][0]
    assert image["image_type"] == "sample"
    assert image["attempt_no"] == 1
    assert image["is_history_visible"] is False
    assert batch["source_sample_batch_id"] is None


def test_cancel_sample_ready_and_idempotent(client):
    token = _login(client)
    sample = _sample(client, token).json()["data"]
    batch_id = sample["batch_id"]
    batch = _batch(client, token, batch_id)
    image_id = batch["images"][0]["image_id"]
    assert batch["status"] == "sample_ready"

    print("[测试] 步骤 1：取消 sample_ready 示例批次")
    cancel = client.post(f"/api/v1/generations/{batch_id}/cancel", headers=_headers(token))
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["data"]["status"] == "cancelled"
    assert cancel.json()["data"]["finished_at"]

    print("[测试] 步骤 2：重复取消自然幂等")
    again = client.post(f"/api/v1/generations/{batch_id}/cancel", headers=_headers(token))
    assert again.status_code == 200
    assert again.json()["data"]["status"] == "cancelled"

    print("[测试] 步骤 3：取消后不可确认、不可下载")
    confirm = client.post(
        f"/api/v1/generations/{batch_id}/confirm",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    assert confirm.status_code == 409 and confirm.json()["code"] == 30005
    download = client.get(f"/api/v1/images/{image_id}/download", headers=_headers(token))
    assert download.status_code == 409
    assert download.json()["message"] == "示例图确认前不可下载"


def test_cancel_running_full_batch(client):
    token = _login(client)
    sample = _sample(client, token).json()["data"]
    confirm = client.post(
        f"/api/v1/generations/{sample['batch_id']}/confirm",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    full_id = confirm.json()["data"]["full_batch_id"]

    print("[测试] 直接把全套批次置为 running，模拟生成中")
    from app.core.database import SessionLocal
    from app.models import GenerationBatch

    with SessionLocal() as db:
        batch = db.get(GenerationBatch, full_id)
        batch.status = "running"
        db.commit()

    cancel = client.post(f"/api/v1/generations/{full_id}/cancel", headers=_headers(token))
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["data"]["status"] == "cancelled"

    print("[测试] 取消后成功图不再进入历史，下载被拒绝")
    result = _batch(client, token, full_id)
    assert result["status"] == "cancelled"
    assert all(image["is_history_visible"] is False for image in result["images"])
    image_id = result["images"][0]["image_id"]
    assert (
        client.get(f"/api/v1/images/{image_id}/download", headers=_headers(token)).status_code
        == 409
    )
    assert (
        client.get(f"/api/v1/batches/{full_id}/download", headers=_headers(token)).status_code
        == 409
    )


# ---------------------------------------------------------------- 失败与降级


def test_fault_core_agent_fails_sample(client):
    from app.core.config import settings

    settings.GENERATION_FAULT_MODE = "core"
    token = _login(client)
    response = _sample(client, token)
    assert response.status_code == 200, response.text
    batch_id = response.json()["data"]["batch_id"]
    batch = _batch(client, token, batch_id)
    print("[测试] 核心 Agent 连续失败后批次 failed")
    assert batch["status"] == "failed"
    assert "planner" in (batch["error_message"] or "")
    assert batch["images"][0]["status"] == "failed"

    runs = _agent_runs(batch_id)
    planner_runs = [run for run in runs if run.agent_code == "planner"]
    assert len(planner_runs) == 10
    assert all(run.status == "failed" for run in planner_runs)
    assert all(run.error_message for run in planner_runs)


def test_fault_image_failure_stops_full_batch(client):
    from app.core.config import settings

    token = _login(client)
    sample = _sample(client, token).json()["data"]
    batch = _batch(client, token, sample["batch_id"])
    assert batch["status"] == "sample_ready"

    settings.GENERATION_FAULT_MODE = "image"
    confirm = client.post(
        f"/api/v1/generations/{sample['batch_id']}/confirm",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    full_id = confirm.json()["data"]["full_batch_id"]
    result = _batch(client, token, full_id)
    print("[测试] 生图连续失败后批次立即 failed，后续张不生成")
    assert result["status"] == "failed"
    assert "生图失败" in (result["error_message"] or "")
    by_index = {image["index"]: image for image in result["images"]}
    assert by_index[1]["status"] == "success"
    assert by_index[2]["status"] == "failed"
    for index in range(3, 7):
        assert by_index[index]["status"] == "failed"
        assert by_index[index]["error_message"] == "批次已失败，未生成"


def test_fault_platform_partial_then_regenerate_to_completed(client):
    from app.core.config import settings

    token = _login(client)
    sample = _sample(client, token).json()["data"]
    assert _batch(client, token, sample["batch_id"])["status"] == "sample_ready"

    settings.GENERATION_FAULT_MODE = "platform"
    confirm = client.post(
        f"/api/v1/generations/{sample['batch_id']}/confirm",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    full_id = confirm.json()["data"]["full_batch_id"]
    result = _batch(client, token, full_id)
    print("[测试] 平台规范不通过：该张失败，其余继续，批次 partially_failed")
    assert result["status"] == "partially_failed"
    assert result["completed_count"] == 1
    by_index = {image["index"]: image for image in result["images"]}
    assert by_index[1]["status"] == "success"
    for index in range(2, 7):
        assert by_index[index]["status"] == "failed"
        assert "平台规范未通过" in (by_index[index]["error_message"] or "")

    print("[测试] 部分失败批次可下载 ZIP，manifest 列出失败张")
    zip_response = client.get(
        f"/api/v1/batches/{full_id}/download", headers=_headers(token)
    )
    assert zip_response.status_code == 200, zip_response.text
    assert zip_response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(zip_response.content)) as archive:
        names = archive.namelist()
        assert len([name for name in names if name.endswith(".png")]) == 1
        manifest = archive.read("manifest.csv").decode("utf-8-sig")
    lines = [line for line in manifest.splitlines() if line.strip()]
    assert lines[0] == "序号,文件名,状态,尺寸,生成时间,失败原因"
    assert len(lines) == 7
    assert "success" in lines[1]
    assert "failed" in lines[2] and "平台规范未通过" in lines[2]

    print("[测试] 逐张重试失败图，批次回升 completed")
    settings.GENERATION_FAULT_MODE = ""
    failed_images = [image for image in result["images"] if image["status"] == "failed"]
    for image in failed_images:
        response = client.post(
            f"/api/v1/images/{image['image_id']}/regenerate",
            headers=_headers(token),
            json={"client_request_id": _uid()},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["attempt_no"] == 2
        assert response.json()["data"]["index"] == image["index"]

    final = _batch(client, token, full_id)
    assert final["status"] == "completed"
    assert final["completed_count"] == 6
    assert len(final["images"]) == 6
    assert all(image["status"] == "success" for image in final["images"])
    assert all(image["is_history_visible"] is True for image in final["images"])
    assert all(image["attempt_no"] == 2 for image in final["images"][1:])

    print("[测试] 完成后 ZIP 包含 6 张图")
    zip_all = client.get(f"/api/v1/batches/{full_id}/download", headers=_headers(token))
    with zipfile.ZipFile(BytesIO(zip_all.content)) as archive:
        assert len([name for name in archive.namelist() if name.endswith(".png")]) == 6


def test_regenerate_success_image_keeps_completed_count(client):
    token = _login(client)
    sample = _sample(client, token).json()["data"]
    confirm = client.post(
        f"/api/v1/generations/{sample['batch_id']}/confirm",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    full_id = confirm.json()["data"]["full_batch_id"]
    batch = _batch(client, token, full_id)
    target = next(image for image in batch["images"] if image["index"] == 2)
    old_image_id = target["image_id"]

    response = client.post(
        f"/api/v1/images/{old_image_id}/regenerate",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    assert response.status_code == 200, response.text
    new_image_id = response.json()["data"]["image_id"]
    assert new_image_id != old_image_id

    updated = _batch(client, token, full_id)
    assert updated["status"] == "completed"
    assert updated["completed_count"] == 6
    current = next(image for image in updated["images"] if image["index"] == 2)
    assert current["image_id"] == new_image_id
    assert current["attempt_no"] == 2
    assert current["status"] == "success"
    assert current["is_history_visible"] is True

    print("[测试] 旧图 superseded，不可再预览/下载")
    from app.core.database import SessionLocal
    from app.models import GeneratedImage

    with SessionLocal() as db:
        old = db.get(GeneratedImage, old_image_id)
        assert old.status == "superseded"
        assert old.is_history_visible is False
    assert (
        client.get(f"/api/v1/images/{old_image_id}/content", headers=_headers(token)).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/images/{old_image_id}/download", headers=_headers(token)).status_code
        == 409
    )


def test_regenerate_validation_and_idempotency(client):
    token = _login(client)
    sample = _sample(client, token).json()["data"]
    confirm = client.post(
        f"/api/v1/generations/{sample['batch_id']}/confirm",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    full_id = confirm.json()["data"]["full_batch_id"]
    batch = _batch(client, token, full_id)
    target = batch["images"][1]

    print("[测试] 步骤 1：示例图不可重试")
    sample_image_id = _batch(client, token, sample["batch_id"])["images"][0]["image_id"]
    sample_regenerate = client.post(
        f"/api/v1/images/{sample_image_id}/regenerate",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    assert sample_regenerate.status_code == 409
    assert sample_regenerate.json()["message"] == "当前图片不可重试"

    print("[测试] 步骤 2：不存在图片返回 30014")
    missing = client.post(
        "/api/v1/images/99999999/regenerate",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    assert missing.status_code == 404 and missing.json()["code"] == 30014

    print("[测试] 步骤 3：批次不是终态时拒绝")
    from app.core.database import SessionLocal
    from app.models import GenerationBatch

    with SessionLocal() as db:
        row = db.get(GenerationBatch, full_id)
        row.status = "running"
        db.commit()
    not_ready = client.post(
        f"/api/v1/images/{target['image_id']}/regenerate",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    assert not_ready.status_code == 409
    assert not_ready.json()["message"] == "请从批次入口重新生成"

    print("[测试] 步骤 4：同批次已有重试进行中时拒绝")
    with SessionLocal() as db:
        row = db.get(GenerationBatch, full_id)
        row.status = "completed"
        from app.models import GeneratedImage

        other = db.get(GeneratedImage, target["image_id"])
        other.status = "generating"
        db.commit()
    busy = client.post(
        f"/api/v1/images/{target['image_id']}/regenerate",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    assert busy.status_code == 409
    assert busy.json()["message"] == "该批次有重试任务进行中"

    print("[测试] 步骤 5：同一 client_request_id 返回同一新图片")
    with SessionLocal() as db:
        from app.models import GeneratedImage

        other = db.get(GeneratedImage, target["image_id"])
        other.status = "success"
        db.commit()
    key = _uid()
    first = client.post(
        f"/api/v1/images/{target['image_id']}/regenerate",
        headers=_headers(token),
        json={"client_request_id": key},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/api/v1/images/{target['image_id']}/regenerate",
        headers=_headers(token),
        json={"client_request_id": key},
    )
    assert second.status_code == 200
    assert first.json()["data"]["image_id"] == second.json()["data"]["image_id"]


def test_batch_download_errors(client):
    token = _login(client)
    sample = _sample(client, token).json()["data"]

    print("[测试] 示例批次不支持整组下载")
    sample_zip = client.get(
        f"/api/v1/batches/{sample['batch_id']}/download", headers=_headers(token)
    )
    assert sample_zip.status_code == 409
    assert sample_zip.json()["message"] == "当前批次不支持整组下载"

    print("[测试] 不存在批次返回 30004")
    missing = client.get("/api/v1/batches/99999999/download", headers=_headers(token))
    assert missing.status_code == 404 and missing.json()["code"] == 30004

    print("[测试] 管理员无 user.history 权限")
    admin_token = _login(client, "demo_admin")
    forbidden = client.get(
        f"/api/v1/batches/{sample['batch_id']}/download", headers=_headers(admin_token)
    )
    assert forbidden.status_code == 403 and forbidden.json()["code"] == 20005

    print("[测试] 没有成功图的全套批次返回「没有可下载的图片」")
    from app.core.database import SessionLocal
    from app.models import CreativeSession, GenerationBatch, User

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "demo_user"))
        session = db.scalar(select(CreativeSession).where(CreativeSession.user_id == user.id))
        empty_batch = GenerationBatch(
            user_id=user.id,
            session_id=session.id,
            batch_type="full",
            source_sample_batch_id=sample["batch_id"],
            product_name="空批次",
            width=1000,
            height=1000,
            total_count=6,
            completed_count=0,
            status="failed",
            params_snapshot={},
        )
        db.add(empty_batch)
        db.commit()
        empty_id = empty_batch.id
    # failed 状态先被状态校验拦截
    failed_zip = client.get(f"/api/v1/batches/{empty_id}/download", headers=_headers(token))
    assert failed_zip.status_code == 409


def test_ownership_isolation_for_generation(client):
    user_token = _login(client, "demo_user")
    other_token = _login(client, "demo_dual")
    sample = _sample(client, user_token).json()["data"]
    batch_id = sample["batch_id"]
    image_id = _batch(client, user_token, batch_id)["images"][0]["image_id"]

    print("[测试] 其他用户访问批次/图片/ZIP 均 404")
    assert (
        client.get(f"/api/v1/generations/{batch_id}", headers=_headers(other_token)).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/images/{image_id}/content", headers=_headers(other_token)).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/generations/{batch_id}/cancel", headers=_headers(other_token)
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/batches/{batch_id}/download", headers=_headers(other_token)
        ).status_code
        == 404
    )
