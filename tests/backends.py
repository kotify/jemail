from collections.abc import Sequence
from typing import ClassVar

from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend


class RecordingEmailBackend(BaseEmailBackend):
    sent: ClassVar[list[EmailMessage]] = []

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        self.sent.extend(email_messages)
        return len(email_messages)
