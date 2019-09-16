from slacker import Slacker

from django.core.management.base import BaseCommand
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.conf import settings

from foiatracker.models import Reminder, Event


DATALAB_URL = 'http://datalab.dallasnews.com/'
REMINDER_MSG = ('Reminder: It\'s time to check in on one of your records '
                'requests: "%s". See the <%s|request on FOIAtracker> for '
                'details and don\'t forget to send updates to '
                '`foia@postbox.dallasnews.com`')


class Command(BaseCommand):
    help = 'Sends all scheduled reminders for FOIAtracker'

    def handle(self, *args, **options):
        reminders = Reminder.objects.filter(
            sent_time=None,
            scheduled_time__lte=timezone.now()
        )

        if not reminders:
            self.stdout.write(self.style.SUCCESS(
                'No FOIA reminders scheduled for sending.'))
            return

        slack = Slacker(settings.SLACK_TOKEN)

        users = slack.users.list()

        user_mappings = {}

        for user in users.body['members']:
            if 'email' in user['profile']:
                user_mappings[user['profile']['email']] = user['id']

        for r in reminders:
            self.stdout.write('Sending reminder for "%s"' % r.foia)
            sender_email = r.foia.email.sender.email

            if r.foia.status()[0] != Event.PENDING:
                print(('Skipping reminder for "%s".' % r.foia))
                continue

            try:
                slack_id = user_mappings[sender_email]
                foia_url = '%s%s' % (DATALAB_URL, reverse(
                    'foia-edit', kwargs={'pk': r.foia.id}))
                slack.chat.post_message(
                    slack_id, REMINDER_MSG % (r.foia, foia_url),
                    username='FOIAtracker', icon_emoji=':foiatracker:'
                )
            except KeyError:
                self.stderr.write(
                    'No Slack pairing found for %s.' % sender_email)

        reminder_count = len(reminders)
        reminders.update(sent_time=timezone.now())

        self.stdout.write(self.style.SUCCESS(
            'Finished sending %s FOIA reminders.' % reminder_count))
