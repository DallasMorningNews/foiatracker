from django.conf.urls import url

from foiatracker.views import (
    create_from_email,
    EventCreateView,
    EventDeleteView,
    EventUpdateView,
    FoiaDeleteView,
    FoiaListView,
    FoiaUpdateView,
    inbound_mail,
    ProjectCreateView,
    ProjectDetailView,
    ProjectListView,
    ProjectUpdateView,
)


urlpatterns = [
    url(r'^mailhook/$', inbound_mail),
    url(r'^$', FoiaListView.as_view(), name='foia-list'),
    url(r'^request/(?P<pk>[0-9]+)/$', FoiaUpdateView.as_view(),
        name='foia-edit'),
    url(r'^request/(?P<pk>[0-9]+)/delete/$', FoiaDeleteView.as_view(),
        name='foia-delete'),
    url(r'^event/add/$', EventCreateView.as_view(),
        name='event-add'),
    url(r'^event/(?P<pk>[0-9]+)/$', EventUpdateView.as_view(),
        name='event-edit'),
    url(r'^event/(?P<pk>[0-9]+)/delete/$', EventDeleteView.as_view(),
        name='event-delete'),
    url(r'^request/from-email/(?P<uuid>[^/]+)/$', create_from_email,
        {'to_create': 'foia'}, name='foia-from-email'),
    url(r'^event/from-email/(?P<uuid>[^/]+)/$', create_from_email,
        {'to_create': 'event'}, name='event-from-email'),
    url(r'^project/add/$', ProjectCreateView.as_view(), name='project-add'),
    url(r'^project/(?P<pk>[0-9]+)/$',
        ProjectDetailView.as_view(), name='project-detail'),
    url(r'^project/(?P<pk>[0-9]+)/edit/$',
        ProjectUpdateView.as_view(), name='project-edit'),
    url(r'^projects/$', ProjectListView.as_view(), name='project-list')
]
