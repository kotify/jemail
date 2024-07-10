from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from .models import EmailAttachment, EmailMessage

DEFAULTS = {
    "METADATA_ID_KEY": "message_id",
    "HTML_MESSAGE_UPLOAD_TO": "emails/messages/",
    "ATTACHMENT_UPLOAD_TO": "emails/attachments/",
}

_SETTINGS = {
    **DEFAULTS,
    **getattr(settings, "JEMAIL", {}),
}

METADATA_ID_KEY = _SETTINGS["METADATA_ID_KEY"]


def HTML_MESSAGE_UPLOAD_TO(obj: EmailMessage, filename: str) -> str:  # noqa [N802]
    if _SETTINGS.get("IMPORT_HTML_MESSAGE_UPLOAD_TO"):
        module, name = _SETTINGS["IMPORT_HTML_MESSAGE_UPLOAD_TO"].rsplit(".", 1)
        return getattr(importlib.import_module(module), name)(obj, filename)
    return os.path.join(_SETTINGS["HTML_MESSAGE_UPLOAD_TO"], filename)


def ATTACHMENT_UPLOAD_TO(obj: EmailAttachment, filename: str) -> str:  # noqa [N802]
    if _SETTINGS.get("IMPORT_ATTACHMENT_UPLOAD_TO"):
        module, name = _SETTINGS["IMPORT_ATTACHMENT_UPLOAD_TO"].rsplit(".", 1)
        return getattr(importlib.import_module(module), name)(obj, filename)
    return os.path.join(_SETTINGS["ATTACHMENT_UPLOAD_TO"], filename)
