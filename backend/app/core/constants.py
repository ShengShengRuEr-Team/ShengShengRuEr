"""业务枚举与占位常量。"""

TASK_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "failed",
    "pending_confirm",
    "completed",
)

DEFAULT_TASK_TYPE = "import_paper"
