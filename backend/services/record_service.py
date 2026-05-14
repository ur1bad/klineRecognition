from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.config import get_config
from backend.db import repository
from backend.utils.date_utils import normalize_date_string


class RecordService:
    def __init__(self) -> None:
        self.config = get_config()

    def normalize_inference_model(self, value: Optional[str]) -> str:
        text = (value or "").strip()
        lowered = text.lower()
        if (
            not text
            or lowered in {"remote_api", "custom_fastapi"}
            or lowered.startswith("qwen2.5-vl + lora")
        ):
            return self.config.remote_api_display_name
        if lowered == "qwen2.5-vl-7b-instruct":
            return self.config.remote_api_display_name
        return text

    def _normalize_record(self, record: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if record is None:
            return None
        cloned = dict(record)
        cloned["inference_model"] = self.normalize_inference_model(cloned.get("inference_model"))
        return cloned

    def create_record(
        self,
        *,
        user_id: int,
        stock_code: Optional[str],
        image_path: Path,
        predicted_label: str,
        confidence: float,
        reason: str,
        source_type: str,
        window_size: Optional[int],
        start_date: Optional[str],
        end_date: Optional[str],
        inference_model: Optional[str],
    ) -> dict[str, Any]:
        record_id = repository.insert_record(
            {
                "user_id": int(user_id),
                "stock_code": stock_code,
                "image_path": str(image_path.resolve()),
                "predicted_label": predicted_label,
                "confidence": confidence,
                "reason": reason,
                "source_type": source_type,
                "window_size": window_size,
                "start_date": normalize_date_string(start_date),
                "end_date": normalize_date_string(end_date),
                "inference_model": self.normalize_inference_model(inference_model),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        record = self._normalize_record(repository.get_record(record_id, user_id=user_id))
        if record is None:
            raise RuntimeError("识别记录写入成功，但回读失败。")
        return record

    def list_records(
        self,
        *,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        stock_code: Optional[str] = None,
        predicted_label: Optional[str] = None,
    ) -> dict[str, Any]:
        items = [
            self._normalize_record(record)
            for record in repository.list_records(
                limit=limit,
                offset=offset,
                user_id=user_id,
                stock_code=stock_code,
                predicted_label=predicted_label,
            )
        ]
        return {
            "total": repository.count_records(
                user_id=user_id,
                stock_code=stock_code,
                predicted_label=predicted_label,
            ),
            "items": [record for record in items if record is not None],
        }

    def get_record(self, record_id: int, *, user_id: int) -> Optional[dict[str, Any]]:
        return self._normalize_record(repository.get_record(record_id, user_id=user_id))

    def delete_record(self, record_id: int, *, user_id: int) -> Optional[dict[str, Any]]:
        record = repository.get_record(record_id, user_id=user_id)
        if record is None:
            return None

        deleted = repository.delete_record(record_id, user_id=user_id)
        image_deleted = False
        if deleted:
            image_deleted = self._delete_managed_image(record.get("image_path"))

        return {
            "record_id": int(record_id),
            "deleted": bool(deleted),
            "image_deleted": image_deleted,
        }

    def delete_records_for_user(self, user_id: int) -> dict[str, int]:
        records_deleted = 0
        images_deleted = 0

        while True:
            records = repository.list_records(limit=500, offset=0, user_id=user_id)
            if not records:
                break

            for record in records:
                deleted = repository.delete_record(int(record["id"]), user_id=user_id)
                if not deleted:
                    continue
                records_deleted += 1
                if self._delete_managed_image(record.get("image_path")):
                    images_deleted += 1

        return {
            "records_deleted": records_deleted,
            "images_deleted": images_deleted,
        }

    def _delete_managed_image(self, image_path_value: Any) -> bool:
        if not image_path_value:
            return False

        try:
            image_path = Path(str(image_path_value)).resolve()
            image_path.relative_to(self.config.outputs_dir.resolve())
        except (OSError, ValueError):
            return False

        if not image_path.is_file():
            return False

        try:
            image_path.unlink()
        except OSError:
            return False
        return True

    def attach_image_url(self, record: dict[str, Any], base_url: str) -> dict[str, Any]:
        cloned = self._normalize_record(record) or {}
        image_path = Path(cloned["image_path"])
        try:
            relative = image_path.resolve().relative_to(self.config.outputs_dir.resolve()).as_posix()
            cloned["image_url"] = f"{base_url.rstrip('/')}{self.config.static_mount_path}/{relative}"
        except ValueError:
            cloned["image_url"] = None
        return cloned

    def is_backtest_ready(self, record: dict[str, Any]) -> bool:
        return bool(record.get("stock_code") and record.get("window_size") and record.get("end_date"))
