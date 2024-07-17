from __future__ import annotations

import datetime as dt

import pytest
from anymail.signals import AnymailTrackingEvent, EventType
from anymail.signals import tracking as tracking_signal
from anymail.webhooks.sendgrid import SendGridTrackingWebhookView

import jemail.settings
from jemail.models import (
    EmailMessage,
    EmailRecipient,
    EmailRecipientKind,
    is_status_transition_allowed,
    is_webhook_event_supported,
)


def from_utc_timestamp(timestamp):
    return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)


@pytest.fixture(autouse=True)
def set_webhook_secret(settings):
    # Just to disable warning.
    settings.ANYMAIL_WEBHOOK_SECRET = "abc:123"


def test_is_webhook_event_supported():
    # No log ids.
    anymail_event = AnymailTrackingEvent(event_type=EventType.CLICKED)
    assert not is_webhook_event_supported(anymail_event)
    # Log ids are empty.
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.CLICKED, metadata={jemail.settings.METADATA_ID_KEY: ""}
    )
    assert not is_webhook_event_supported(anymail_event)
    # OK.
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.CLICKED, metadata={jemail.settings.METADATA_ID_KEY: "abc"}
    )
    assert is_webhook_event_supported(anymail_event)
    # Event is not supported.
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.COMPLAINED,
        metadata={jemail.settings.METADATA_ID_KEY: "abc"},
    )
    assert not is_webhook_event_supported(anymail_event)


def test_is_status_transition_allowed():
    # Empty
    assert is_status_transition_allowed("", "any")
    # Tracking events
    assert is_status_transition_allowed("any", EventType.CLICKED)
    assert is_status_transition_allowed("any", EventType.OPENED)
    # To deferred
    assert is_status_transition_allowed(EventType.QUEUED, EventType.DEFERRED)
    # To delivered
    assert is_status_transition_allowed(EventType.QUEUED, EventType.DELIVERED)
    assert is_status_transition_allowed(EventType.DEFERRED, EventType.DELIVERED)
    # To bounced
    assert is_status_transition_allowed(EventType.QUEUED, EventType.BOUNCED)
    assert is_status_transition_allowed(EventType.DEFERRED, EventType.BOUNCED)
    assert is_status_transition_allowed(EventType.DELIVERED, EventType.BOUNCED)
    # To rejected
    assert is_status_transition_allowed(EventType.QUEUED, EventType.REJECTED)
    assert is_status_transition_allowed(EventType.DEFERRED, EventType.REJECTED)
    # Impossible from deferred
    assert not is_status_transition_allowed(EventType.DEFERRED, EventType.QUEUED)
    # Impossible from delivered
    assert not is_status_transition_allowed(EventType.DELIVERED, EventType.QUEUED)
    assert not is_status_transition_allowed(EventType.DELIVERED, EventType.DEFERRED)
    assert not is_status_transition_allowed(EventType.DELIVERED, EventType.REJECTED)
    # Impossible from bounced
    assert not is_status_transition_allowed(EventType.BOUNCED, EventType.QUEUED)
    assert not is_status_transition_allowed(EventType.BOUNCED, EventType.DEFERRED)
    assert not is_status_transition_allowed(EventType.BOUNCED, EventType.DELIVERED)
    assert not is_status_transition_allowed(EventType.BOUNCED, EventType.REJECTED)
    # Impossible from rejected
    assert not is_status_transition_allowed(EventType.REJECTED, EventType.QUEUED)
    assert not is_status_transition_allowed(EventType.REJECTED, EventType.DEFERRED)
    assert not is_status_transition_allowed(EventType.REJECTED, EventType.BOUNCED)
    assert not is_status_transition_allowed(EventType.REJECTED, EventType.DELIVERED)
    # To the same status
    assert not is_status_transition_allowed(EventType.QUEUED, EventType.QUEUED)
    assert not is_status_transition_allowed(EventType.DEFERRED, EventType.DEFERRED)
    assert not is_status_transition_allowed(EventType.BOUNCED, EventType.BOUNCED)
    assert not is_status_transition_allowed(EventType.REJECTED, EventType.REJECTED)
    assert not is_status_transition_allowed(EventType.DELIVERED, EventType.DELIVERED)


def test_fill_from_anymail_event_tracking_not_exist():
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.BOUNCED,
        timestamp=from_utc_timestamp(1),
        esp_event={"data": "abc"},
        recipient="test@example.com",
    )
    recipient = EmailRecipient(timestamp=None)
    recipient.fill_from_anymail_event(anymail_event)
    assert recipient.status == EventType.BOUNCED
    assert recipient.timestamp
    assert recipient.timestamp.timestamp() == 1
    assert recipient.clicks_count == 0
    assert recipient.opens_count == 0


def test_fill_from_anymail_event_old_event():
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.QUEUED, timestamp=from_utc_timestamp(1)
    )
    recipient = EmailRecipient(
        status=EventType.BOUNCED, timestamp=from_utc_timestamp(2)
    )
    recipient.fill_from_anymail_event(anymail_event)
    assert recipient.status == EventType.BOUNCED
    assert recipient.timestamp
    assert recipient.timestamp.timestamp() == 2


def test_fill_from_anymail_event_new_event():
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.REJECTED, timestamp=from_utc_timestamp(2)
    )
    recipient = EmailRecipient(status=EventType.QUEUED, timestamp=from_utc_timestamp(1))
    recipient.fill_from_anymail_event(anymail_event)
    assert recipient.status == EventType.REJECTED
    assert recipient.timestamp
    assert recipient.timestamp.timestamp() == 2


def test_fill_from_anymail_event_click_event():
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.CLICKED, timestamp=from_utc_timestamp(2)
    )
    recipient = EmailRecipient(status=EventType.QUEUED, timestamp=from_utc_timestamp(1))
    recipient.fill_from_anymail_event(anymail_event)
    assert recipient.status == EventType.QUEUED
    assert recipient.timestamp
    assert recipient.timestamp.timestamp() == 1
    assert recipient.clicks_count == 1
    assert recipient.opens_count == 0


def test_fill_from_anymail_event_first_event_is_open():
    """Test that the first open event is handled."""
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.OPENED,
        timestamp=from_utc_timestamp(1),
        esp_event={"data": "abc"},
        recipient="test@example.com",
    )
    recipient = EmailRecipient(timestamp=None)
    recipient.fill_from_anymail_event(anymail_event)
    assert recipient.status == EventType.DELIVERED
    assert recipient.address == ""
    assert recipient.timestamp is None
    assert recipient.clicks_count == 0
    assert recipient.opens_count == 1


def test_fill_from_anymail_event_old_open_event():
    anymail_event = AnymailTrackingEvent(
        event_type=EventType.OPENED, timestamp=from_utc_timestamp(1)
    )
    recipient = EmailRecipient(status=EventType.QUEUED, timestamp=from_utc_timestamp(2))
    recipient.fill_from_anymail_event(anymail_event)
    assert recipient.status == EventType.QUEUED
    assert recipient.timestamp
    assert recipient.timestamp.timestamp() == 2
    assert recipient.clicks_count == 0
    assert recipient.opens_count == 1


def test_fill_from_anymail_event_open_delivered_events():
    """Test events received in the same batch and include `open` and `delivered` events."""
    open_anymail_event = AnymailTrackingEvent(
        event_type=EventType.OPENED, timestamp=from_utc_timestamp(2)
    )
    delivered_anymail_event = AnymailTrackingEvent(
        event_type=EventType.DELIVERED, timestamp=from_utc_timestamp(1)
    )
    recipient = EmailRecipient()
    # Most recent event goes first in batch.
    recipient.fill_from_anymail_event(open_anymail_event)
    recipient.fill_from_anymail_event(delivered_anymail_event)
    assert recipient.status == EventType.DELIVERED
    assert recipient.timestamp
    assert recipient.timestamp.timestamp() == 1
    assert recipient.opens_count == 1


def test_handle_sendgrid_events(db):
    """
    Integration test for events handling.
    Check sendgrid events are correctly handled.
    Test that delivered event is handled before the queued.
    """
    email = "test@example.com"
    em = EmailMessage.objects.create()
    EmailRecipient.objects.create(address=email, message=em, kind=EmailRecipientKind.TO)
    data = [
        {
            "email": email,
            jemail.settings.METADATA_ID_KEY: str(em.pk),
            "event": EventType.DELIVERED,
            "timestamp": 1,
        },
        {
            "email": email,
            jemail.settings.METADATA_ID_KEY: str(em.pk),
            "event": EventType.QUEUED,
            "timestamp": 1,
        },
    ]
    view = SendGridTrackingWebhookView()
    qs = EmailRecipient.objects.all()
    for item in data:
        tracking_signal.send(
            sender=view, event=view.esp_to_anymail_event(item), esp_name="SendGrid"
        )
        assert qs.count() == 1
    recipient = qs.get()
    assert recipient.status == EventType.DELIVERED
    assert recipient.address == email
    assert recipient.timestamp
    assert recipient.timestamp.timestamp() == 1
    assert recipient.clicks_count == 0
    assert recipient.opens_count == 0
