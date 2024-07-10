# Jemail

Django app to store emails in db


## Installation

```sh
pip install jemail
pip install django-anymail[sendgrid]
```

Anymail used as email backend, for now jemail tested only with `sendgrid` backend.

Update settings with:

```python
EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"

# defaults
JEMAIL = {
    "METADATA_ID_KEY": "message_id",  # tag name for EmailMessage.pk in message metadata
    "HTML_MESSAGE_UPLOAD_TO": "emails/messages/",  # path to save html messages to
    "ATTACHMENT_UPLOAD_TO": "emails/attachments/",  # path to save attachments to
    # "IMPORT_HTML_MESSAGE_UPLOAD_TO": "myproject.utils.message_upload_to",  # callable option
    # "IMPORT_ATTACHMENT_UPLOAD_TO": "myproject.utils.attachment_upload_to",  # callable option
}
```

## Usage

```python
from jemail import EmailMessage, EmailAttachment

# save email in db
message = EmailMessage.objects.create_with_objects(
    from_email='no-reply@example.com',
    to=['user@example.com'],
    subject='Subject',
    body='Hi User,...',
    html_message='<p>Hi User...',
    cc=['cc@example.com'],
    reply_to='support@example.com',
    attachments=[EmailAttachment.objects.create(
        filename='doc.pdf',
        mimetype='application/pdf',
        file=ContentFile(b'...', name='doc.pdf')
    )],

# build EmailMultiAlternatives from db
msg = message.build_message()
# send email
msg.send()
)
```

## Development

nix-direnv:

```sh
echo "use flake" >> .envrc
direnv allow
app.install
pytest
```

nix:

```sh
nix develop
app.install
pytest
```

uv:

```sh
uv -q venv .venv
source .venv/bin/activate
uv pip install -e .[dev,test]
pre-commit install
pytest
```
