from django.contrib.postgres.search import SearchQuery
from django.contrib.postgres.search import SearchRank
from django.contrib.postgres.search import SearchVector
from django.db.models import OuterRef
from django.db.models import Subquery

from django_filters import CharFilter
from django_filters import FilterSet

from foiatracker.models import Event
from foiatracker.models import Foia


class FoiaFilter(FilterSet):
    sender = CharFilter(name='email__sender__email')
    search = CharFilter(method='search_filter')
    status = CharFilter(method='status_filter')

    def search_filter(self, queryset, field, search_term):
        """Use Django's Postgres full-text search integration to search
        the subject, notes fields and original e-mail"""
        vector = (
            SearchVector('request_subject',
                         'agency_id',
                         'notes', weight='A') +
            SearchVector('recipients__name',
                         'recipients__organization',
                         'email__sender__first_name',
                         'email__sender__last_name', weight='B') +
            SearchVector('email__text',
                         'email__sender__email',
                         'recipients__email', weight='C')
        )
        return queryset.annotate(
            rank=SearchRank(vector, SearchQuery(search_term))
        ).filter(
            rank__gte=0.1
        ).order_by('-rank')

    def status_filter(self, queryset, field, status):
        """Filter requests by whether they have been resolved (denied,
        no responsive records, etc.)"""
        qs = queryset.annotate(
            latest_status=Subquery(
                Event.objects.filter(
                    foia=OuterRef('pk')
                ).order_by(
                    '-update_date'
                ).values(
                    'status'
                )[:1]
            )
        )

        if status == 'pending':
            return qs.exclude(latest_status__in=Event.COMPLETE)
        elif status == 'complete':
            return qs.filter(latest_status__in=Event.COMPLETE)
        return qs.none()

    class Meta:
        model = Foia
        fields = []
