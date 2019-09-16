from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save

from foiatracker.models import Foia, Recipient, Sender
from foiatracker.tasks import post_new_foia_slack


@receiver(post_save, dispatch_uid="foiatracker_slack", sender=Foia)
def foia_to_slack(sender, instance, **kwargs):
    # Dump out here if the save method has been told not to send a Slack
    # notification
    if instance.slack_notify is False:
        return

    post_new_foia_slack.delay(instance.pk)


@receiver(pre_save, dispatch_uid="hydrate_from_rolodex", sender=Recipient)
def hydrate_from_rolodex(sender, instance, **kwargs):
    """Before saving our Recipient instance for the first time, get all
    the info we can from the Rolodex API"""
    instance.sync_with_rolodex()


@receiver(pre_save, dispatch_uid="hydrate_from_staff_api", sender=Sender)
def hydrate_from_staff_api(sender, instance, **kwargs):
    """Pull contact info from staff API if we don't have it already"""
    if instance.pk:
        return

    instance.sync_with_staff_api()
