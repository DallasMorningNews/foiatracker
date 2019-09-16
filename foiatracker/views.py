from email.utils import parseaddr, parsedate_tz, mktime_tz, getaddresses

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.timezone import datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView
from django.views.generic.edit import UpdateView, CreateView, DeleteView

from django_filters.views import FilterView

from foiatracker.models import (
    EmailAttachment,
    Foia,
    Sender,
    InboundEmail,
    Project,
    Recipient,
    Event
)
from foiatracker.filters import FoiaFilter
from foiatracker.forms import (EventModelForm, ReminderFoiaFormSet,
                               FoiaForm)
from foiatracker.utils import (verify_mailgun_token, tz_aware_date,
                               get_model_by_email)
from foiatracker import tasks


class FoiaListView(LoginRequiredMixin, FilterView):
    queryset = Foia.objects.all().\
        select_related('email', 'email__sender', 'project').\
        prefetch_related('event_set', 'recipients')
    filterset_class = FoiaFilter
    paginate_by = 15

    def drop_param(self, param):
        """Drop the named param from our existing list of GET params"""
        url_params = self.request.GET.copy()
        try:
            url_params.pop(param)
        except KeyError:
            pass
        return url_params

    def build_url(self, url_params):
        """Encode and attach the passed url_params to our current URL"""
        if url_params:
            return '?'.join((
                self.request.path,
                url_params.urlencode(),
            ))
        return self.request.path

    def filter_link(self, context, filter_, value):
        """Add links for manipulationg a filter to the passed context"""
        url_params = self.request.GET.copy()
        url_params[filter_] = value
        filter_name = 'filter_%s_%s' % (filter_, value,)

        # A link to set the filter to the passed value
        context['%s_link' % filter_name] = self.build_url(url_params)

        # A boolean to let us know if the filter is set to the passed value
        context['%s_active' % filter_name] = (
            self.filterset.data.get(filter_) == value
        )

        # A link to clear the filter
        context['filter_%s_clear' % filter_] = self.build_url(
            self.drop_param(filter_)
        )

    def get_page_title(self, context):
        parts = [
            'My' if context['filter_me_active'] else 'All',
        ]

        if context['filter_status_complete_active']:
            parts.append('resolved')
        elif context['filter_status_pending_active']:
            parts.append('pending')

        parts.append('requests')

        if self.filterset.data.get('search'):
            parts.append('matching "%s"' % self.filterset.data.get('search'))

        return ' '.join(parts)

    def get_context_data(self, **kwargs):
        context = super(FoiaListView, self).get_context_data(**kwargs)
        context['active_filters'] = self.filterset.data

        # Get all the URL params except page= and pass them down so we can
        # append them to our pagination, which will persist filters across
        # pages
        context['filter_params'] = self.drop_param('page').urlencode()

        # Generate a link to clear the search
        context['clear_search_url'] = self.build_url(self.drop_param('search'))

        # Links to set all/my requests filters
        url_params = self.request.GET.copy()
        url_params['sender'] = self.request.user.email
        context['filter_me'] = self.build_url(url_params)

        context['filter_all'] = self.build_url(self.drop_param('sender'))

        # Set a boolean to indicate if we're on the "My reqeusts" filtered view
        context['filter_me_active'] = (self.filterset.data.get('sender') ==
                                       self.request.user.email)

        # Links to filter by request status
        self.filter_link(context, 'status', 'complete')
        self.filter_link(context, 'status', 'pending')

        context['page_title'] = self.get_page_title(context)

        return context


class FoiaUpdateView(LoginRequiredMixin, UpdateView):
    success_url = reverse_lazy('foia-list')
    form_class = FoiaForm
    queryset = Foia.objects.all().select_related(
        'email'
    ).prefetch_related(
        'event_set__email__attachments'
    )

    def get_context_data(self, **kwargs):
        context = super(FoiaUpdateView, self).get_context_data(**kwargs)
        if self.request.POST:
            context['reminders'] = ReminderFoiaFormSet(self.request.POST,
                                                       instance=self.object)
        else:
            context['reminders'] = ReminderFoiaFormSet(
                instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        reminders_formset = context['reminders']
        if reminders_formset.is_valid() and form.is_valid():
            self.object = form.save()
            reminders_formset.instance = self.object
            reminders_formset.save()
            success_message = 'Request "%s" updated.' % \
                self.object
            messages.success(self.request, success_message)
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))


class FoiaDeleteView(LoginRequiredMixin, DeleteView):
    model = Foia
    success_url = reverse_lazy('foia-list')

    def delete(self, request, *args, **kwargs):
        """Override the delete() behavior from the base class to queue up a
        success message"""
        success_message = 'Request successfully deleted.'
        messages.success(request, success_message)
        return super(FoiaDeleteView, self).delete(request, *args, **kwargs)


class EventCreateView(SuccessMessageMixin, LoginRequiredMixin, CreateView):
    model = Event
    success_url = reverse_lazy('foia-list')
    form_class = EventModelForm
    success_message = "Status updated for \"%(foia)s\""

    def get_initial(self):
        self.initial = {}

        if self.request.GET:
            email_uuid = self.request.GET.get('email')
            try:
                self.email = InboundEmail.objects.get(uuid=email_uuid)
                self.initial['email'] = self.email.pk
                self.initial['update_date'] = self.email.sent.date()
            except InboundEmail.DoesNotExist:
                pass

            self.initial['foia'] = self.request.GET.get('foia')

        return self.initial

    def get_context_data(self, **kwargs):
        context = super(EventCreateView, self).get_context_data(**kwargs)
        if hasattr(self, 'email'):
            context['email'] = self.email
        return context


class EventUpdateView(SuccessMessageMixin, LoginRequiredMixin, UpdateView):
    model = Event
    success_url = reverse_lazy('foia-list')
    form_class = EventModelForm
    success_message = "Status saved for \"%(foia)s\""

    def get_context_data(self, **kwargs):
        context = super(EventUpdateView, self).get_context_data(**kwargs)
        # Set this context to match EventCreateForm to simplify templating
        if context['event'].email:
            context['email'] = context['event'].email
        return context


class EventDeleteView(LoginRequiredMixin, DeleteView):
    model = Event
    success_url = reverse_lazy('foia-list')

    def delete(self, request, *args, **kwargs):
        """Override the delete() behavior from the base class to queue up a
        success message"""
        success_message = 'Request status update successfully deleted.'
        messages.success(request, success_message)
        return super(EventDeleteView, self).delete(request, *args, **kwargs)


class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    success_url = reverse_lazy('project-list')
    success_message = "Created new project \"%(project)s\""
    fields = ('name', 'description', 'collaborators',)


class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    model = Project
    success_url = reverse_lazy('project-list')
    success_message = "Project \"%(project)s\" updated."
    fields = ('name', 'description', 'collaborators',)


class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project

    def get_context_data(self, **kwargs):
        context = super(
            ProjectDetailView, self).get_context_data(**kwargs)

        context['recent_updates'] = Event.objects.filter(
            foia__project__pk=context['project'].pk
        ).select_related('foia')

        context['pending_requests'] = Foia.objects.filter(
            event__foia__project__pk=context['project'].pk
        ).exclude(
            event__status__in=Event.COMPLETE
        ).distinct()
        context['finished_requests'] = Foia.objects.filter(
            event__status__in=Event.COMPLETE,
            event__foia__project__pk=context['project'].pk
        ).distinct()

        return context


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    paginate_by = 10


@require_GET
def create_from_email(request, uuid=None, to_create=None):
    """A route to handle creating of Events/Foias based on a UUID of an
    InboundEmail"""
    if to_create not in ('foia', 'event',):
        return HttpResponseBadRequest()

    email = get_object_or_404(InboundEmail.objects, uuid=uuid)

    # See if the e-mail has already been processed by looking for associated
    # Foias/Events and redirect there
    try:
        existing_foia = Foia.objects.get(email=email)
        return redirect('foia-edit', pk=existing_foia.pk)
    except Foia.DoesNotExist:
        pass

    try:
        existing_event = Event.objects.get(email=email)
        return redirect('event-edit', pk=existing_event.pk)
    except Event.DoesNotExist:
        pass

    # For FOIAs we'll go ahead and create the model and then send the user
    # straight to the model's edit page
    if to_create == 'foia':
        foia = Foia(email=email, request_subject=email.subject,
                    sent=email.sent.date())
        foia.save(slack_notify=False)
        # Copy recipients from the e-mail to give users something to start
        # with
        foia.recipients = email.recipients.all()
        foia.save(slack_notify=False)

    if to_create == 'foia':
        messages.success(
            request,
            'We\'ve auto-created request "%s" from your e-mail.' % foia
        )
        return redirect('foia-edit', pk=foia.pk)

    # For event instances, we'll send them to an add page and pre-load the
    # current e-mail into to the context/initial form state
    msg = 'Please answer a few more questions about "%s" to help us \
        understand your e-mail and choose a records request to pair it with.\
        ' % email.subject
    messages.success(request, msg)
    return redirect("%s?email=%s" % (reverse('event-add'), email.uuid))


@require_POST
@csrf_exempt
def inbound_mail(request):
    """Parse an inbound Mailgun event (https://documentation.mailgun.com/
    quickstart-receiving.html) and save the data as models"""
    if not verify_mailgun_token(request.POST.get('token'),
                                request.POST.get('timestamp'),
                                request.POST.get('signature')):
            return HttpResponseForbidden('Failed Mailgun token validation.')

    required_fields = ('sender', 'To', 'Date',)
    missing_fields = [x for x in required_fields if x not in request.POST]

    if missing_fields:
        return HttpResponseBadRequest('Missing a requied field.')

    # Parse the out sender/recipient fields
    sender_address = parseaddr(request.POST.get('sender'))
    recipient_addresses = getaddresses(request.POST.get('To').split(','))

    if sender_address[1].split('@')[1] not in \
            settings.FOIATRACKER_ALLOWED_DOMAINS:
        msg = '"%s" is not authorized to use FOIAtracker.' % sender_address[1]
        return HttpResponseForbidden(msg)

    # Make a timezone-aware datetime from the Date field
    date_field = request.POST.get('Date')
    parsed_from_email = parsedate_tz(date_field)
    if parsed_from_email is not None:
        parsed_timestamp = mktime_tz(parsed_from_email)
        parsed_datetime = datetime.fromtimestamp(parsed_timestamp)
    else:
        parsed_datetime = datetime.now()
    sent = tz_aware_date(parsed_datetime)

    # Create a model for the email
    email = InboundEmail.objects.create(
        raw=request.POST.get('body-plain', ''),
        text=request.POST.get('stripped-text', ''),
        html=request.POST.get('body-html', ''),
        sent=sent,
        sender=get_model_by_email(Sender, sender_address[1]),
        subject=request.POST.get('subject', '')
    )

    # Setup M2M relationships for email recipeints
    for address in recipient_addresses:
        # For addresses that aren't e-mails, like 'undisclosed-recipients'
        if '@' not in address[1]:
            continue

        if address[1].split('@')[1] in settings.FOIATRACKER_ALLOWED_DOMAINS:
            continue

        recipient = get_model_by_email(
            Recipient,
            address[1]
        )
        email.recipients.add(recipient)

    email.save()

    # Send a message to let the user know we're ready to classify
    tasks.email_prompt(email.pk)

    # Save file attachments to S3 and attach them to the message
    attachment_count = request.POST.get('attachment-count')

    if attachment_count is not None:
        try:
            num_attachments = int(attachment_count)

            for attachment_num in range(1, num_attachments + 1):
                attachment_key = 'attachment-%s' % attachment_num
                attached_file = request.FILES.get(attachment_key)

                if attached_file is None:
                    continue

                EmailAttachment.objects.create(
                    email=email,
                    stored_file=attached_file,
                    content_type=attached_file.content_type,
                    size=attached_file.size
                )
        except ValueError:
            pass

    return HttpResponse()
