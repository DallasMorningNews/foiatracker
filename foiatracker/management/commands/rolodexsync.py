from django.core.management.base import BaseCommand

from foiatracker.models import Recipient


class Command(BaseCommand):
    help = 'Syncs all request recipients with the Rolodex API'

    def handle(self, *args, **options):
        for r in Recipient.objects.all():
            self.stdout.write('Syncing "%s"' % r.email)
            r.save()
        self.stdout.write(self.style.SUCCESS(
            'Finished syncing recipient information with Rolodex.'))
