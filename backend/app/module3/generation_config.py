"""Frozen text generation capacity shared by identity and cost reservation."""

MAX_OUTPUT = 4096


def generation_parameters():
    return {
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": MAX_OUTPUT,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
