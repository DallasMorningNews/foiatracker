from datetime import time, timedelta, datetime
from os import path
import uuid

from holidays import US
import requests

from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify

from foiatracker import utils
from foiatracker.custom_storages import FoiatrackerAttachmentStorage


class Sender(models.Model):
    STAFF_API_URL = 'http://datalab.dallasnews.com/staff/api/'

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)

    def __str__(self):
        if self.first_name and self.last_name:
            return '%s %s' % (self.first_name, self.last_name)
        else:
            return self.email

    def sync_with_staff_api(self):
        api_req_url = '%sstaff/%s' % (self.STAFF_API_URL, self.email)
        r = requests.get(api_req_url)

        if r.status_code != requests.codes.ok:
            # TODO: Log API error here
            return

        staffer_info = r.json()

        try:
            self.first_name = staffer_info['firstName']
            self.last_name = staffer_info['lastName']
        except KeyError:
            # TODO: Log that the staffer wasn't found
            pass

    class Meta:
        ordering = ('last_name', 'first_name',)


class Recipient(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, blank=True)
    organization = models.CharField(max_length=255, blank=True)

    rolodex_person_id = models.PositiveSmallIntegerField(null=True)
    rolodex_contact_id = models.PositiveSmallIntegerField(null=True)
    rolodex_organization_id = models.PositiveSmallIntegerField(null=True)

    def __str__(self):
        if self.name and self.organization:
            return '%s (%s)' % (self.organization, self.name)
        elif self.name:
            return self.name
        elif self.organization:
            return self.organization
        return self.email

    def __rolodex_url(self, endpoint, item_id):
        if item_id is None:
            return None
        return '%s/api/%s/%s/' % (settings.FOIATRACKER_ROLODEX_URL, endpoint,
                                  item_id)

    def has_rolodex_match(self):
        return self.rolodex_person_id is not None or \
            self.rolodex_organization_id is not None
    has_rolodex_match.boolean = True

    @property
    def rolodex_person_url(self):
        return self.__rolodex_url('people', self.rolodex_person_id)

    @property
    def rolodex_contact_url(self):
        return self.__rolodex_url('contacts', self.rolodex_contact_id)

    @property
    def rolodex_organization_url(self):
        return self.__rolodex_url('orgs', self.rolodex_organization_id)

    def sync_with_rolodex(self):
        # Try the contacts/ endpoint
        rolodex_contact = utils.query_rolodex_by_email(self.email)
        if rolodex_contact is None:
            self.name = self.organization = ''
            self.rolodex_contact_id = self.rolodex_person_id = \
                self.rolodex_organization_id = None
            return
        self.rolodex_contact_id = rolodex_contact['id']

        # Try the orgs/ endpoint first for contacts that may tied directly
        # to an organization
        if rolodex_contact['org'] is not None:
            self.rolodex_organization_id = utils.get_id_from_rolodex_url(
                rolodex_contact['org']
            )
            org = utils.get_from_rolodex(self.rolodex_organization_url)
            if org is not None:
                self.name = ''
                self.rolodex_person_id = None
                self.organization = org['orgName']
                return

        # Try the people/ endpoint
        if rolodex_contact['person'] is None:
            self.name = self.organization = ''
            self.rolodex_person_id = self.rolodex_organization_id = None
            return
        self.rolodex_person_id = utils.get_id_from_rolodex_url(
            rolodex_contact['person'])
        person = utils.get_from_rolodex(self.rolodex_person_url)
        if person is None:  # API/HTTP error
            self.name = self.organization = ''
            self.rolodex_person_id = self.rolodex_organization_id = None
            return
        self.name = '%s %s' % (person['firstName'], person['lastName'])

        # Try the orgs/ endpoint
        if not person['org_relations']:
            self.organization = ''
            self.rolodex_organization_id = None
            return
        self.rolodex_organization_id = utils.get_id_from_rolodex_url(
            person['org_relations'][0])
        organization = utils.get_from_rolodex(self.rolodex_organization_url)
        if organization is not None:
            self.organization = organization['orgName']

    class Meta:
        ordering = ['email', ]


class InboundEmail(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True,
                            editable=False)
    raw = models.TextField()
    text = models.TextField()
    html = models.TextField(verbose_name='HTML')

    recipients = models.ManyToManyField(Recipient, blank=True)
    sender = models.ForeignKey(Sender, on_delete=models.PROTECT)
    sent = models.DateTimeField()
    processed = models.BooleanField(default=False, editable=False)

    subject = models.CharField(max_length=255)

    def create_foia_url(self):
        """A route that will create a FOIA from this email object"""
        return reverse('foia-from-email', kwargs={'uuid': self.uuid})

    def create_event_url(self):
        """A route that will create an Event from this email object"""
        return reverse('event-from-email', kwargs={'uuid': self.uuid})

    def __str__(self):
        if self.subject:
            return self.subject
        return '- no subject -'

    def recipients_str(self):
        strs = [str(x) for x in self.recipients.all()]
        return ', '.join(strs)
    recipients_str.short_description = 'Recipients'


class EmailAttachment(models.Model):
    email = models.ForeignKey(
        InboundEmail, on_delete=models.CASCADE, related_name='attachments')
    stored_file = models.FileField(
        upload_to='%Y/%m/',
        storage=FoiatrackerAttachmentStorage()
    )
    content_type = models.CharField(max_length=100, blank=True, null=True)
    size = models.PositiveIntegerField(null=True)

    @property
    def download_url(self):
        return self.stored_file.storage.url(self.stored_file.name)

    @property
    def filename(self):
        return path.basename(self.stored_file.name)

    @property
    def icon(self):
        if not self.content_type or '/' not in self.content_type:
            return 'file'

        type_parts = self.content_type.split('/')

        allowed_types = (
            'excel', 'pdf', 'sound', 'word', 'archive', 'image', 'photo',
            'zip', 'audio', 'text', 'code', 'powerpoint', 'video',
        )

        if self.content_type == 'application/octet-stream':
            return 'file'
        elif type_parts[0] == 'image':
            return 'file-image-o'
        elif type_parts[1] in allowed_types:
            return 'file-%s-o' % type_parts[1]
        elif 'spreadsheet' in type_parts[1] or 'excel' in type_parts[1]:
            return 'file-excel-o'
        elif 'html' in type_parts[1]:
            return 'file-code-o'
        else:
            return 'file-o'


class Foia(models.Model):
    email = models.ForeignKey(InboundEmail, on_delete=models.CASCADE)
    sent = models.DateField()
    recipients = models.ManyToManyField(Recipient)
    request_subject = models.CharField(
        max_length=255,
        help_text='Example: Dallas ISD annual audit'
    )
    notes = models.TextField(blank=True)
    notified = models.BooleanField(default=False)
    project = models.ForeignKey(
        'Project',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='requests'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False
    )
    agency_id = models.CharField(
        blank=True,
        help_text='The agency\'s internal ID number for this request',
        max_length=20,
        verbose_name='agency ID'
    )

    class Meta:
        verbose_name = 'FOIA'
        verbose_name_plural = 'FOIAs'
        ordering = ['-sent', '-created_at', ]

    def __str__(self):
        return self.request_subject

    def add_event_url(self):
        return '%s?foia=%s' % (reverse('event-add'), self.id)

    def status(self):
        recent_event = self.event_set.first()
        if recent_event:
            return recent_event.status, recent_event.get_status_display()
        else:
            return (Event.PENDING, 'Awaiting agency response')

    def due(self):
        return utils.add_business_days(11, from_datetime=self.sent)

    def recipients_str(self):
        if self.recipients.count():
            strs = [str(x) for x in self.recipients.all()]
            return ', '.join(strs)
        else:
            return self.email.recipients_str()
    recipients_str.short_description = 'Recipients'

    def save(self, slack_notify=True, *args, **kwargs):
        # Store this here so post_save signals can pick it up
        self.slack_notify = slack_notify

        # Add a default reminder to each FOIA that's 10 business days in the
        # future at 10 a.m. on the first save
        new = (self.pk is None)

        super(Foia, self).save(*args, **kwargs)

        if new:
            morning = time(hour=10, minute=00)
            reminder_time = utils.tz_aware_date(datetime.combine(
                self.due(), morning))
            Reminder.objects.create(foia=self, scheduled_time=reminder_time)


class Event(models.Model):
    PENDING = 'pending'
    KICKED = 'kicked'
    DENIED = 'denied'
    RELEASED_BY_ATG = 'relatg'
    PARTIALLY_RELEASED_BY_AGENCY = 'paragc'
    RELEASED_BY_AGENCY = 'relagc'
    WITHDRAWN = 'wthdrwn'
    NO_RECORDS = 'norecs'
    STATUS_CHOICES = (
        (PENDING, 'Awaiting agency response'),
        (KICKED, 'Kicked to attorney general'),
        (DENIED, 'Denied by attorney general'),
        (RELEASED_BY_ATG, 'Released by attorney general'),
        (PARTIALLY_RELEASED_BY_AGENCY, 'Partially released by agency',),
        (RELEASED_BY_AGENCY, 'Released by agency'),
        (NO_RECORDS, 'No responsive records'),
        (WITHDRAWN, 'Withdrawn')
    )

    COMPLETE = (DENIED, RELEASED_BY_AGENCY, WITHDRAWN, NO_RECORDS)

    email = models.ForeignKey(InboundEmail, null=True,
                              on_delete=models.CASCADE)
    update_date = models.DateField()
    status = models.CharField(max_length=7, choices=STATUS_CHOICES,
                              default=PENDING)
    amount_asked = models.PositiveIntegerField(null=True, blank=True)
    amount_paid = models.PositiveIntegerField(null=True, blank=True)
    foia = models.ForeignKey(Foia, on_delete=models.CASCADE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return self.get_status_display()

    @property
    def business_days_since_request(self):
        days_since = self.update_date - self.foia.sent
        work_days_since = 0

        tx_holidays = US(state='TX')

        for day_num in range(days_since.days):
            day = self.foia.sent + timedelta(days=day_num)
            if day not in tx_holidays and day.weekday() < 5:
                work_days_since += 1

        return timedelta(days=work_days_since)

    class Meta:
        ordering = ['-update_date', '-created_at', ]


class Reminder(models.Model):
    scheduled_time = models.DateTimeField(blank=True, null=True)
    sent_time = models.DateTimeField(blank=True, null=True)
    foia = models.ForeignKey(Foia, on_delete=models.CASCADE)


class Project(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField()
    slug = models.SlugField()
    collaborators = models.ManyToManyField(Sender, related_name='projects')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Generate a unique slug using the project name"""
        slug = slugify(self.name)

        additional_number = 2
        unique = False

        while not unique:
            try:
                existing_project = Project.objects.get(slug=slug)

                if existing_project == self:
                    unique = True
                else:
                    slug = slugify('%s-%s' % (self.name, additional_number,))
                    additional_number += 1
            except Project.DoesNotExist:
                unique = True

        self.slug = slug

        super(Project, self).save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at', ]
