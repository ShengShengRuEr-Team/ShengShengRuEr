"""统一的业务异常与响应外壳辅助。"""

from typing import Any



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
        401,
        msg,
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden(required_role: str = "管理员") -> AppError:
    return AppError(
        403,
        f"没有访问该接口的权限：需要{required_role}角色",
    )


def not_found(msg: str = "资源不存在") -> AppError:
    return AppError(404, msg)


def bad_request(msg: str) -> AppError:
    return AppError(400, msg)


def ok(data: Any = None, msg: str = "获取成功") -> dict[str, Any]:
    return {"code": 200, "msg": msg, "data": data}
