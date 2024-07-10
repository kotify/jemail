from __future__ import annotations

import email.utils
import logging
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, cast

import django.dispatch
import html2text
from anymail.message import AnymailMessageMixin, AnymailRecipientStatus
from anymail.signals import EventType
from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.core.mail.message import EmailMultiAlternatives
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from . import settings

logger = logging.getLogger(__name__)
jemail_message_status_update = django.dispatch.Signal()

if TYPE_CHECKING:
    from collections.abc import Sequence


class EmailRecipientKind(models.IntegerChoices):
    TO = 0, "to"
    CC = 1, "cc"
    BCC = 2, "bcc"


class TrackingEventProtocol(Protocol):
    recipient: str
    timestamp: Any
    event_type: Any  # EventType
    metadata: dict[str, Any]


class EmailAttachment(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now=True, editable=False)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
    )
    filename = models.CharField(_("name"), max_length=256)
    file = models.FileField(
        verbose_name=_("file"),
        upload_to=settings.ATTACHMENT_UPLOAD_TO,
        max_length=512,
    )
    mimetype = models.CharField(_("MIME type"), max_length=128)


def _normalize_email_list(addrs: Sequence[str], seen: Sequence[str]) -> list[str]:
    result: list[str] = []
    for addr in addrs:
        laddr = addr.lower()
        if laddr not in result and laddr not in seen:
            result.append(laddr)
    return result


def _fix_email_recipient_duplication(
    to: Sequence[str],
    cc: Sequence[str] | None = None,
    bcc: Sequence[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    to = _normalize_email_list(to, [])
    cc = _normalize_email_list(cc or [], to)
    bcc = _normalize_email_list(bcc or [], to + (cc or []))
    return to, cc, bcc


class EmailMessageQuerySet(models.QuerySet["EmailMessage"]):
    def with_has_attachments(self) -> EmailMessageQuerySet:
        return self.annotate(
            has_attachments=models.Exists(
                EmailMessageAttachment.objects.filter(message_id=models.OuterRef("pk"))
            )
        )

    def build_messages(
        self, *, html_message: str | bytes | None = None
    ) -> list[JemailMessage]:
        qs = self.prefetch_related("recipients", "attachments")
        return [obj.build_message(hint_html_message=html_message) for obj in qs]


class EmailMessageManager(models.Manager["EmailMessage"]):
    def create_with_objects(
        self,
        from_email: str,
        to: Sequence[str],
        subject: str,
        body: str,
        html_message: str | None = None,
        cc: Sequence[str] | None = None,
        bcc: Sequence[str] | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
        reply_to: str | None = None,
    ) -> EmailMessage:
        to, cc, bcc = _fix_email_recipient_duplication(to, cc, bcc)
        from_email_name, from_email = email.utils.getaddresses([from_email])[0]
        if reply_to:
            reply_to_name, reply_to = email.utils.getaddresses([reply_to])[0]
        else:
            reply_to_name = reply_to = ""
        # optimization to generate html_message path and pass it to create
        html_message_path = ""
        if html_message is not None:
            _em = EmailMessage()
            _em.html_message.save(
                "body.html", ContentFile(html_message.encode("utf-8")), save=False
            )
            html_message_path = _em.html_message.name
        message = super().create(
            from_email=from_email,
            from_email_name=from_email_name,
            subject=subject,
            body=body,
            reply_to=reply_to,
            reply_to_name=reply_to_name,
            html_message=html_message_path,
        )
        # fmt: off
        EmailRecipient.objects.bulk_create(
            [
                *[EmailRecipient(message=message, address=address, kind=EmailRecipientKind.TO) for address in to],
                *[EmailRecipient(message=message, address=address, kind=EmailRecipientKind.CC) for address in cc],
                *[EmailRecipient(message=message, address=address, kind=EmailRecipientKind.BCC) for address in bcc],
            ]
        )
        # fmt: on
        if attachments:
            message.attachments.set(attachments)
        return message


class JemailMessage(AnymailMessageMixin, EmailMultiAlternatives):
    def __init__(self, dbmessage: EmailMessage, **kwargs: Any):
        self.dbmessage = dbmessage
        super().__init__(**kwargs)

    def send(self, fail_silently: bool = False) -> int:
        result = super().send(fail_silently=fail_silently)
        if result == 0 and fail_silently is True:
            return result
        recipients = {r.address: r for r in self.dbmessage.recipients.all()}
        statuses = cast(
            dict[str, AnymailRecipientStatus],
            self.anymail_status.recipients,
        )
        for address, status in statuses.items():
            recipients[address].status = status.status
            recipients[address].provider_id = status.message_id
        EmailRecipient.objects.filter(status="").bulk_update(
            recipients.values(), fields=["status", "message_id"]
        )
        return result


class EmailMessage(models.Model):
    recipients: models.Manager[EmailRecipient]

    created_at = models.DateTimeField(_("created at"), auto_now=True, editable=False)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
    )
    from_email = models.EmailField(_("from email"))
    from_email_name = models.CharField(_("from email name"), max_length=128)
    reply_to = models.EmailField(_("reply-to email"), blank=True)
    reply_to_name = models.CharField(_("reply-to name"), blank=True, max_length=128)
    subject = models.TextField(_("email subject"))
    body = models.TextField(_("email text"), blank=True)
    attachments: models.ManyToManyField[EmailAttachment, EmailMessageAttachment] = (
        models.ManyToManyField(
            EmailAttachment,
            through="EmailMessageAttachment",
            verbose_name=_("attachments"),
            related_name="messages",
        )
    )
    html_message = models.FileField(
        verbose_name=_("html message"),
        upload_to=settings.HTML_MESSAGE_UPLOAD_TO,
        blank=True,
    )

    objects: ClassVar[EmailMessageManager] = EmailMessageManager.from_queryset(  # pyright: ignore
        EmailMessageQuerySet
    )()

    def build_message(
        self,
        hint_html_message: str | bytes | None = None,
        hint_attachments: Sequence[EmailAttachment] | None = None,
    ) -> JemailMessage:
        _attachments = (
            self.attachments.all() if hint_attachments is None else hint_attachments
        )
        attachments = [
            (a.filename, a.file.file.read(), a.mimetype) for a in _attachments
        ]
        if hint_html_message is None:
            html_message = self.html_message.read().decode("utf-8")
        elif isinstance(hint_html_message, str):
            html_message = hint_html_message
        elif isinstance(hint_html_message, bytes):
            html_message = hint_html_message.decode("utf-8")
        else:
            raise ValueError(
                f"Type {type(hint_html_message)} is not supported for `hint_html_message`."
            )
        body = self.body or html2text.html2text(html_message)
        to: list[str] = []
        cc: list[str] = []
        bcc: list[str] = []
        for r in self.recipients.all():
            if r.kind == EmailRecipientKind.TO:
                to.append(r.address)
            elif r.kind == EmailRecipientKind.CC:
                cc.append(r.address)
            elif r.kind == EmailRecipientKind.BCC:
                bcc.append(r.address)
        msg = JemailMessage(
            dbmessage=self,
            subject=self.subject,
            body=body,
            from_email=email.utils.formataddr((self.from_email_name, self.from_email)),
            to=to,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            reply_to=[email.utils.formataddr((self.reply_to_name, self.reply_to))]
            if self.reply_to
            else None,
        )
        if html_message:
            msg.attach_alternative(html_message, "text/html")
        msg.metadata = {settings.METADATA_ID_KEY: str(self.pk)}
        return msg


class EmailRecipient(models.Model):
    message_id: int
    message = models.ForeignKey(
        EmailMessage,
        related_name="recipients",
        on_delete=models.CASCADE,
        verbose_name=_("message"),
        db_index=False,
    )
    address = models.EmailField(_("email address"))
    provider_id = models.CharField(
        _("mail service provider recipient's id"), max_length=128
    )
    kind = models.PositiveSmallIntegerField(
        _("recipient kind"), choices=EmailRecipientKind.choices
    )
    # anymail's EventType
    status = models.CharField(max_length=32, verbose_name=_("mail delivery status"))
    timestamp = models.DateTimeField(
        verbose_name=_("latest delivery event time"), null=True
    )
    clicks_count = models.PositiveSmallIntegerField(
        verbose_name=_("clicks count"), default=0
    )
    opens_count = models.PositiveSmallIntegerField(
        verbose_name=_("opens count"), default=0
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "address"],
                name="jemail_message_has_unique_recipients",
            ),
            models.CheckConstraint(
                check=models.Q(address=Lower("address")),
                name="jemail_address_in_lowercase",
            ),
        ]

    @staticmethod
    def is_delivery_event(status: str) -> bool:
        return status in {
            EventType.BOUNCED,
            EventType.DEFERRED,
            EventType.DELIVERED,
            EventType.REJECTED,
            EventType.QUEUED,
        }

    def _fill_from_delivery_anymail_event(
        self, anymail_event: TrackingEventProtocol
    ) -> None:
        if (
            # First event handled
            self.timestamp is None
            # Events may have equal timestamps, but different types.
            or self.timestamp <= anymail_event.timestamp
        ):
            self.status = anymail_event.event_type
            self.timestamp = anymail_event.timestamp

    def fill_from_anymail_event(self, anymail_event: TrackingEventProtocol) -> None:
        if self.is_delivery_event(anymail_event.event_type):
            self._fill_from_delivery_anymail_event(anymail_event)
        else:
            # Tracking events are the first when they are received
            # in the single batch with other delivery events.
            # So delivery events will be processed soon and the correct data will be set.
            self.status = self.status or EventType.DELIVERED
            if anymail_event.event_type == EventType.CLICKED:
                self.clicks_count += 1
            if anymail_event.event_type == EventType.OPENED:
                self.opens_count += 1


def is_webhook_event_supported(anymail_event: TrackingEventProtocol) -> bool:
    return (
        anymail_event.event_type
        in [
            EventType.BOUNCED,
            EventType.DEFERRED,
            EventType.DELIVERED,
            EventType.REJECTED,
            EventType.QUEUED,
            EventType.CLICKED,
            EventType.OPENED,
        ]
        # Email belongs to MagiLoop.
        and bool(anymail_event.metadata.get(settings.METADATA_ID_KEY))
    )


# Delivery status allowed transitions.
# Key is the source status, value is allowed destination statuses.
DELIVERY_STATUS_TRANSITION_MAP = {
    EventType.QUEUED: [
        EventType.DELIVERED,
        EventType.BOUNCED,
        EventType.REJECTED,
        EventType.DEFERRED,
    ],
    EventType.DEFERRED: [EventType.DELIVERED, EventType.BOUNCED, EventType.REJECTED],
    # It's rare case, but email can be bounced after delivery.
    # E.g. "Recipient address rejected: Access denied", "Requested mail action aborted, mailbox not found".
    EventType.DELIVERED: [EventType.BOUNCED],
    # Final statuses
    EventType.BOUNCED: [],
    EventType.REJECTED: [],
}


def is_status_transition_allowed(current_status: str, new_status: str) -> bool:
    """
    Check if tracking object can be transited from one status to another.

    `current_status` is always the delivery status. We store only delivery statuses in db.
    `new_status` is any supported status. It's a webhook event status.
    """
    if not current_status:
        # New object, any status is allowed.
        return True
    if new_status in [EventType.CLICKED, EventType.OPENED]:
        # Tracking events are always allowed.
        # Object is transited to delivered state.
        return True
    return new_status in DELIVERY_STATUS_TRANSITION_MAP[current_status]


def process_mail_event(anymail_event: TrackingEventProtocol) -> None:
    if not is_webhook_event_supported(anymail_event):
        return
    message_id = anymail_event.metadata[settings.METADATA_ID_KEY]
    address = anymail_event.recipient
    # Update `email_tracking.status` only if the `anymail_event.timestamp` is greater than `email_tracking.timestamp`
    # or if `email_tracking.timestamp` is empty
    # Locking `EmailDialogMessage` with `select_for_update` to prevent status update race condition
    with transaction.atomic():
        try:
            recipient = (
                EmailRecipient.objects.filter(message_id=message_id, address=address)
                .select_for_update()
                .get()
            )
        except EmailRecipient.DoesNotExist:
            logger.warning(
                f"Email reciepient for tracking event not found. {settings.METADATA_ID_KEY}: {message_id}, email: {address}"
            )
            return
        if is_status_transition_allowed(recipient.status, anymail_event.event_type):
            recipient.fill_from_anymail_event(anymail_event)
            recipient.save()
        else:
            return
    jemail_message_status_update.send_robust(
        sender=process_mail_event, recipient=recipient
    )


class EmailMessageAttachment(models.Model):
    message = models.ForeignKey(
        EmailMessage,
        verbose_name=_("message"),
        related_name="+",
        on_delete=models.CASCADE,
        db_index=False,
    )
    attachment = models.ForeignKey(
        EmailAttachment,
        verbose_name=_("attachment"),
        related_name="+",
        on_delete=models.CASCADE,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("message", "attachment"),
                name="jemail_unique_message_attachment",
            )
        ]
