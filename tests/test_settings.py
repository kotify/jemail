import jemail.settings
from jemail.models import EmailAttachment, EmailMessage


def test_upload_to_attachments(monkeypatch):
    monkeypatch.setitem(
        jemail.settings._SETTINGS,
        "IMPORT_ATTACHMENT_UPLOAD_TO",
        "tests.example.utils.upload_to",
    )
    att = EmailAttachment(id=300)
    assert (
        jemail.settings.ATTACHMENT_UPLOAD_TO(att, "test.pdf")
        == "upload-to/300/test.pdf"
    )


def test_upload_to_message(monkeypatch):
    monkeypatch.setitem(
        jemail.settings._SETTINGS,
        "IMPORT_HTML_MESSAGE_UPLOAD_TO",
        "tests.example.utils.upload_to",
    )
    em = EmailMessage(id=100)
    assert (
        jemail.settings.HTML_MESSAGE_UPLOAD_TO(em, "testx.pdf")
        == "upload-to/100/testx.pdf"
    )
