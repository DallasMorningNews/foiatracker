from django.contrib import admin

from foiatracker.models import (
    EmailAttachment,
    Event,
    Foia,
    InboundEmail,
    Project,
    Recipient,
    Reminder,
    Sender,
)


class EmailAttachmentInline(admin.TabularInline):
    model = EmailAttachment


@admin.register(InboundEmail)
class InboundEmailAdmin(admin.ModelAdmin):
    readonly_fields = ('raw', 'html', 'uuid',)
    list_display = ('__str__', 'recipients_str', 'sender', 'sent')
    list_filter = ('sender', 'sent')
    search_fields = ('subject', 'text',)
    fieldsets = (
        (None, {
            'fields': ('subject', 'sender', 'recipients', 'text', 'sent',)
        }),
        ('Debugging information', {
            'classes': ('collapse',),
            'fields': ('uuid', 'html', 'raw',),
        }),
    )
    inlines = [
        EmailAttachmentInline,
    ]
    filter_horizontal = (
        'recipients',
    )

    def get_queryset(self, request):
        return InboundEmail.objects.prefetch_related('recipients')


@admin.register(Foia)
class FoiaAdmin(admin.ModelAdmin):
    list_display = ('request_subject', 'sent', 'project',)
    list_filter = ('email__sender', 'email__sent', 'project',)
    list_select_related = ('email__sender', 'project',)
    search_fields = (
        'email__subject',
        'email__text',
        'request_subject',
        'project__name',
    )
    filter_horizontal = (
        'recipients',
    )


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('status', 'foia', 'email', 'created_at',)
    list_filter = ('status', 'created_at',)
    list_select_related = ('email', 'foia',)
    search_fields = (
        'foia__request_subject',
        'email__subject',
        'foia__project__name',
    )
    fieldsets = (
        (None, {
            'fields': ('email', 'foia',)
        }),
        (None, {
            'fields': ('update_date', 'status',)
        }),
        (None, {
            'fields': ('amount_asked', 'amount_paid')
        })
    )


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    pass


@admin.register(Sender)
class SenderAdmin(admin.ModelAdmin):
    readonly_fields = ('first_name', 'last_name',)
    list_display = ('email', 'first_name', 'last_name',)
    list_display_links = ('email',)
    search_fields = ('first_name', 'last_name', 'email',)


def sync_with_rolodex(modeladmin, request, queryset):
    for obj in queryset:
        obj.save()
sync_with_rolodex.short_description = "Sync selected recipients with Rolodex"


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {
            'fields': ('name', 'organization', 'email')
        }),
        ('Debugging information', {
            'classes': ('collapse',),
            'fields': ('rolodex_contact_id', 'rolodex_person_id',
                       'rolodex_organization_id',),
        }),
    )
    readonly_fields = ('name', 'organization', 'rolodex_contact_id',
                       'rolodex_person_id', 'rolodex_organization_id',)
    list_display = ('name', 'email', 'organization', 'has_rolodex_match',
                    'foias_received_count')
    search_fields = ('name', 'email', 'organization',)
    list_filter = ('organization',)
    list_display_links = ('email',)
    actions = [sync_with_rolodex]

    def foias_received_count(self, obj):
        return obj.foia_set.count()
    foias_received_count.short_description = 'Requests received'


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug',)
    search_fields = ('name', 'slug', 'description',)
