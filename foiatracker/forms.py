import re

from fuzzywuzzy import fuzz

from django.forms import (
    DateTimeField,
    ModelChoiceField,
    ModelForm,
    RadioSelect
)
from django.forms import inlineformset_factory
from django.forms import widgets
from django.forms.fields import TypedChoiceField

from foiatracker.models import (
    Event,
    Foia,
    InboundEmail,
    Project,
    Recipient,
    Reminder,
)
from foiatracker.fields import RecipientsChoiceField


DATE_FORMAT = '%A, %b %d, %Y'

DATETIME_FORMAT = '%I:%M%p %A, %b %d, %Y'


class InboundEmailForm(ModelForm):
    sent = DateTimeField(
        input_formats=(DATETIME_FORMAT,),
        widget=widgets.DateTimeInput(format=DATETIME_FORMAT))

    class Meta:
        model = InboundEmail
        fields = ('recipients', 'sent',)


class FoiaForm(ModelForm):
    sent = DateTimeField(
        input_formats=(DATE_FORMAT,),
        widget=widgets.DateTimeInput(format=DATE_FORMAT))
    recipients = RecipientsChoiceField(
        queryset=Recipient.objects.all())

    def clean_recipients(self):
        return self.cleaned_data['recipients']

    class Meta:
        model = Foia
        fields = (
            'email',
            'request_subject',
            'recipients',
            'sent',
            'notes',
            'project',
            'agency_id',
        )


class EventModelForm(ModelForm):
    update_date = DateTimeField(
        input_formats=(DATE_FORMAT,),
        widget=widgets.DateTimeInput(format=DATE_FORMAT))
    foia = TypedChoiceField(
        empty_value=None, initial=None,
        coerce=lambda pk: Foia.objects.get(pk=pk))
    email = ModelChoiceField(
        queryset=InboundEmail.objects.all(), required=False,
        widget=widgets.HiddenInput)

    def __init__(self, *args, **kwargs):
        super(EventModelForm, self).__init__(*args, **kwargs)

        if 'initial' in kwargs and 'email' in kwargs['initial']:
            email = InboundEmail.objects.filter(
                pk=kwargs['initial']['email']
            ).select_related('sender').first()

            sender_projects = Project.objects.filter(
                collaborators=email.sender).values_list('pk', flat=True)

            prefix_re = re.compile('(re|fwd):', flags=re.IGNORECASE)
            generic_language_re = re.compile(
                r'((?:tpia|record(?:s)*|foia|public\s+information)\s+request)(?!\s+log(?:s)*)',
                flags=re.IGNORECASE | re.VERBOSE)

            def strip_subject(subject):
                prefix_removed = prefix_re.sub('', subject)
                generics_removed = generic_language_re.sub('', prefix_removed)
                return ''.join(
                    _ for _ in generics_removed if _.isalpha() or _ == ' ')

            cleaned_email_subject = strip_subject(email.subject)

            def match_email_to_foia(foia):
                score = fuzz.ratio(
                    strip_subject(foia['request_subject']),
                    cleaned_email_subject,
                )

                # Boost the score if the sender is the same and for requests
                # that are in one of the sender's projects
                if foia['email__sender__pk'] == email.sender.pk:
                    score += 25
                elif foia['project__pk'] is not None and \
                        foia['project__pk'] in sender_projects:
                    score += 20

                days_apart = (email.sent.date() - foia['sent']).days

                # Penalize requests that are older than 30 days, but max out
                # the penalty at the 180-day mark
                min_days = 30
                max_days = 180
                normalized_days_apart = min(
                    max(min_days, days_apart), max_days) - min_days
                score *= (1 - float(normalized_days_apart) / float(max_days))

                return score

            all_foias = Foia.objects.all().select_related(
                'email', 'email__sender'
            ).values(
                'pk', 'sent', 'request_subject', 'email__sender__pk',
                'email__sender__last_name', 'project__pk',
            )

            for foia in all_foias:
                foia['label'] = '%s: %s' % (
                    foia['email__sender__last_name'], foia['request_subject'],
                )

            ranked_foias = sorted(
                all_foias, key=match_email_to_foia, reverse=True)

            self.fields['foia'].choices = [
                (f['pk'], f['label'],) for f in ranked_foias
            ]
        else:
            self.fields['foia'].choices = Foia.objects.all().select_related(
                'email__sender'
            ).values_list('pk', 'request_subject')

    class Meta:
        model = Event
        fields = ('foia', 'status', 'update_date', 'amount_asked',
                  'amount_paid', 'notes', 'email',)
        widgets = {
            'status': RadioSelect(choices=Event.STATUS_CHOICES)
        }


class InlineReminderForm(ModelForm):
    scheduled_time = DateTimeField(
        input_formats=(DATETIME_FORMAT,),
        widget=widgets.DateTimeInput(format=DATETIME_FORMAT))

    def __init__(self, *args, **kwargs):
        """If the reminder has already been sent, disable the scheduled_time
        field"""
        super(InlineReminderForm, self).__init__(*args, **kwargs)
        if self.instance.sent_time is not None:
            self.fields['scheduled_time'].disabled = True
            sent_time = self.instance.sent_time.strftime(DATETIME_FORMAT)
            self.fields['scheduled_time'].help_text = 'Sent %s' % sent_time

    class Meta:
        model = Reminder
        fields = ('scheduled_time',)


ReminderFoiaFormSet = inlineformset_factory(
    Foia, Reminder, max_num=1, form=InlineReminderForm
)
