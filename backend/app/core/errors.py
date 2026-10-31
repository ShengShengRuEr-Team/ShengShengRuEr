"""统一的业务异常与响应外壳辅助。"""

from typing import Any

from fastapi import status


class AppError(Exception):
    """可转换为统一响应外壳的业务异常。"""

    def __init__(
        self,
        status_code: int,
        msg: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(msg)
        self.status_code = status_code
        self.msg = msg
        self.headers = headers


def unauthorized(msg: str = "未登录或登录已失效") -> AppError:
    return AppError(
        status.HTTP_401_UNAUTHORIZED,
        msg,
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden(permission_code: str) -> AppError:
    return AppError(
        status.HTTP_403_FORBIDDEN,
        f"没有访问该接口的权限：{permission_code}",
    )


def not_found(msg: str = "资源不存在") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, msg)


def bad_request(msg: str) -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, msg)


def ok(data: Any = None, msg: str = "获取成功") -> dict[str, Any]:
    return {"code": status.HTTP_200_OK, "msg": msg, "data": data}
