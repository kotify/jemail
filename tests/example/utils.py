from typing import Any


def upload_to(obj: Any, filename: str):
    return f"upload-to/{obj.id}/{filename}"
