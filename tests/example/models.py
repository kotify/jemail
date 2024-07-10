from anymail.signals import tracking as tracking_signal
from django.dispatch import receiver

from jemail.models import process_mail_event


@receiver(tracking_signal)
def r(sender, event, **kwargs):
    process_mail_event(event)
