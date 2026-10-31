"""整组 ZIP 与 `manifest.csv` 构建。

契约见 5 号接口文档 §9，与 4 号 demo 08 共用；4 号模块接入时直接调用
`build_batch_zip`，不要另写一套。
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import ApiError
from app.models.workspace import GeneratedImage, GenerationBatch
from app.modules.history.service import HISTORY_BATCH_STATUSES, is_visible_image
from app.modules.workspace.service import (
    filename_timestamp,
    image_download_filename,
    read_image_bytes,
    safe_filename_part,
    to_iso,
)

MANIFEST_HEADER = ("序号", "文件名", "状态", "宽度", "高度", "生成时间", "失败原因")


@dataclass
class BatchZip:
    """已构建完成的 ZIP 流与下载文件名。"""

    stream: BinaryIO
    filename: str


def _get_download_batch(db: Session, user_id: int, batch_id: int) -> GenerationBatch:
    """整组下载的批次校验；不存在 404、越权 403、状态不允许 409。"""
    batch = db.get(GenerationBatch, batch_id)
    if batch is None:
        raise ApiError(404, 30004, "批次不存在")
    if batch.user_id != user_id:
        raise ApiError(403, 20005, "无权限")
    if batch.batch_type != "full" or batch.status not in HISTORY_BATCH_STATUSES:
        raise ApiError(409, 30005, "当前批次不可下载")
    return batch


def _latest_attempts(db: Session, batch_id: int) -> dict[int, GeneratedImage]:
    """每个序号取 `attempt_no` 最大、且非 `superseded` 的记录。"""
    rows = db.scalars(
        select(GeneratedImage)
        .where(
            GeneratedImage.batch_id == batch_id,
            GeneratedImage.status != "superseded",
        )
        .order_by(
            GeneratedImage.index_no.asc(),
            GeneratedImage.attempt_no.desc(),
            GeneratedImage.id.desc(),
        )
    )
    latest: dict[int, GeneratedImage] = {}
    for image in rows:
        latest.setdefault(image.index_no, image)
    return latest


def _image_filename(batch: GenerationBatch, image: GeneratedImage) -> str:
    """与单张下载共用同一命名规则。"""
    return image_download_filename(
        batch.product_name,
        image.image_role,
        image.index_no,
        image.created_at,
    )


def _manifest_text(
    batch: GenerationBatch,
    latest: dict[int, GeneratedImage],
    filenames: dict[int, str],
) -> bytes:
    """构建 UTF-8 BOM 的中文表头 manifest。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(MANIFEST_HEADER)

    for index in range(1, batch.total_count + 1):
        image = latest.get(index)
        if image is not None and is_visible_image(image):
            writer.writerow(
                (
                    index,
                    filenames[index],
                    "success",
                    image.width if image.width is not None else "",
                    image.height if image.height is not None else "",
                    to_iso(image.created_at),
                    "",
                )
            )
            continue
        reason = (image.error_message or "").strip() if image else ""
        writer.writerow((index, "", "failed", "", "", "", reason or "生成失败"))

    return ("﻿" + buffer.getvalue()).encode("utf-8")


def build_batch_zip(db: Session, user_id: int, batch_id: int) -> BatchZip:
    """同步构建整组 ZIP；任一图片不可读时不返回残缺包。"""
    batch = _get_download_batch(db, user_id, batch_id)
    latest = _latest_attempts(db, batch.id)

    success_rows = [
        image
        for index in range(1, batch.total_count + 1)
        if (image := latest.get(index)) is not None and is_visible_image(image)
    ]
    if not success_rows:
        raise ApiError(409, 30005, "没有可下载的图片")

    filenames = {image.index_no: _image_filename(batch, image) for image in success_rows}

    # 先写入可自动转磁盘的临时文件，避免把整个 ZIP 常驻内存
    spool = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    try:
        with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for image in success_rows:
                # 归档件由 read_image_bytes 统一处理超时、缺失与错误日志
                archive.writestr(filenames[image.index_no], read_image_bytes(image))
            archive.writestr(
                "manifest.csv",
                _manifest_text(batch, latest, filenames),
            )
        spool.seek(0)
    except Exception:
        spool.close()
        raise

    zip_filename = (
        f"{safe_filename_part(batch.product_name)}_全套_"
        f"{filename_timestamp(batch.created_at)}.zip"
    )
    return BatchZip(stream=spool, filename=zip_filename)
