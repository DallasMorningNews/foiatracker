from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.template.loader import get_template
from django.urls import reverse
from django.utils.dateformat import format as date_format
from django.utils.html import strip_tags

from celery import shared_task
from slacker import Slacker

from foiatracker.models import Foia, InboundEmail


def get_slack():
    try:
        api_token = settings.SLACK_TOKEN
        return Slacker(api_token)
    except AttributeError:
        raise ImproperlyConfigured(
            'foiatracker requires a SLACK_TOKEN in settings.py'
        )


def get_slack_user(email):
    slack = get_slack()
    users = cache.get_or_set('slack_users', slack.users.list, 3600)
    for user in users.body['members']:
        if 'email' in user['profile']:
            if user['profile']['email'] == email:
                return user['name'], user['profile']['image_24']
    return None, None


@shared_task
def post_new_foia_slack(instance_pk):
    instance = Foia.objects.get(pk=instance_pk)

    # Drop out now if we've already sent a Slack notification or if there
    # aren't any recipients set yet
    if instance.notified is True or instance.recipients.count() == 0:
        return

    slack = get_slack()

    msg = "%s just submitted a records request to %s" % (
        instance.email.sender, instance.recipients_str(),
    )
    foia_edit_url = ''.join((
        'https://datalab.dallasnews.com',
        reverse('foia-edit', kwargs={'pk': instance.pk}),
    ))

    attachments = {
        'title': instance.request_subject,
        'title_link': foia_edit_url,
        'color': '#568C2F',
        'fields': [{
            'title': 'Recipient(s)',
            'value': instance.recipients_str(),
            'short': True
        }, {
            'title': 'Response due',
            'value': date_format(instance.due(), 'N j'),
            'short': True
        }, {
            'title': 'Request',
            'value': instance.email.text[0:50],
            'short': False
        }]
    }

    slack_user, slack_img = get_slack_user(instance.email.sender.email)

    if slack_user:
        team_domain = cache.get('slack_team')

        if team_domain is None:
            team_domain = slack.team.info().body['team']['domain']
            cache.set('slack_team', team_domain, 3600)

        attachments.update(
            author_name=str(instance.email.sender),
            author_icon=slack_img,
            author_link='https://%s.slack.com/team/%s' % (
                team_domain,
                slack_user,
            ),
        )

    slack.chat.post_message(
        settings.FOIATRACKER_SLACK_CHANNEL,
        msg,
        as_user=False,
        icon_emoji=':foiatracker:',
        username='FOIAtracker',
        attachments=[attachments, ],
    )

    # Set our flag so we don't re-notify
    instance.notified = True
    instance.save()


def email_prompt(email_id):
    email = InboundEmail.objects.get(pk=email_id)

    recipients = recipients = [str(x) for x in email.recipients.all()]

    base_url = 'http://datalab.dallasnews.com/'

    html_msg = get_template('foiatracker/email_prompt.html').render({
        'recipients': recipients,
        'new_url': "%s%s" % (base_url, email.create_foia_url()),
        'existing_url': "%s%s" % (base_url, email.create_event_url()),
        'email_subject': email.subject
    })

    send_mail(
        'Help us understand "%s"' % email.subject,
        strip_tags(html_msg),
        'FOIAtracker <newsapps@dallasnews.com>',
        [email.sender.email],
        html_message=html_msg,
        fail_silently=True
    )
