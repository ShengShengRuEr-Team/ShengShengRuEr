"""管理端公共模型：分页与展示时间格式。"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")


def to_display_time(value: datetime) -> str:
    """统一转为 Asia/Shanghai 的带时区 ISO 字符串（入库仍为 UTC）。"""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(DISPLAY_TZ).isoformat()


class PageData[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
