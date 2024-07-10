from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from jemail.models import EmailAttachment, EmailMessage, EmailRecipientKind


def test_create_minimal(db, mailoutbox, settings):
    EmailMessage.objects.create_with_objects(
        to=["user@example.com"],
        subject="Subject",
    )
    em = EmailMessage.objects.get()
    msg = em.build_message()
    assert msg.send() == 1
    assert len(mailoutbox) == 1
    msg = mailoutbox[0]
    assert msg.to == ["user@example.com"]
    assert msg.subject == "Subject"
    assert msg.body == ""
    assert msg.from_email == settings.DEFAULT_FROM_EMAIL


def test_create_with_objects(db, mailoutbox):
    user = User.objects.create(username="user1")
    EmailMessage.objects.create_with_objects(
        to=["user@example.com"],
        subject="Subject",
        # if body not provided it derived from html_message
        # using html2text library
        body="Hi User,...",
        html_message="<p>Hi User...",
        # the rest is optional
        from_email="no-reply@example.com",
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        attachments=[
            EmailAttachment.objects.create(
                filename="doc.pdf",
                mimetype="application/pdf",
                file=ContentFile(b"...", name="doc.pdf"),
            )
        ],
        reply_to=["Example Team <support@example.com>"],
        created_by_id=user.pk,
    )
    em = EmailMessage.objects.get()
    assert em.from_email == "no-reply@example.com"
    assert em.subject == "Subject"
    assert em.body == "Hi User,..."
    assert em.html_message.read() == b"<p>Hi User..."
    assert em.html_message.name.startswith("emails/messages/body")
    assert em.reply_to == ["Example Team <support@example.com>"]
    assert em.created_by == user
    recipients = em.recipients.all()

    assert [r.address for r in recipients if r.kind == EmailRecipientKind.TO] == [
        "user@example.com"
    ]
    assert [r.address for r in recipients if r.kind == EmailRecipientKind.CC] == [
        "cc@example.com"
    ]
    assert [r.address for r in recipients if r.kind == EmailRecipientKind.BCC] == [
        "bcc@example.com"
    ]
    msg = em.build_message()
    assert msg.send() == 1
    assert len(mailoutbox) == 1
    msg = mailoutbox[0]
    assert msg.from_email == "no-reply@example.com"
    assert msg.subject == "Subject"
    assert msg.body == "Hi User,..."
    assert len(msg.alternatives) == 1
    assert msg.reply_to == ["Example Team <support@example.com>"]
