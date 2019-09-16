# -*- coding: utf8 -*-
import os
import datetime
from mock import patch
import json

from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from django.db.models.signals import pre_save, post_save
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.core.management import call_command
from django.utils.six import StringIO

from slacker import Slacker

from foiatracker.models import Foia, InboundEmail, Recipient, Sender
from foiatracker.signals import (
    foia_to_slack,
    hydrate_from_rolodex,
    hydrate_from_staff_api,
)
from foiatracker.tasks import get_slack, get_slack_user
from foiatracker.utils import (
    find_contact_by_email,
    get_from_rolodex,
    get_id_from_rolodex_url,
    get_model_by_email,
    query_rolodex_by_email,
    tz_aware_date,
)


class SenderTestCase(SimpleTestCase):
    def test_str_method_w_email(self):
        """Return full name, if we have it"""
        full_name = Sender(first_name='First', last_name='Last',
                           email='a@example.com')
        self.assertEqual(str(full_name), 'First Last')

    def test_str_method_no_name(self):
        """When there's no name, str() should return e-mail only"""
        email_no_name = Sender(email='a@example.com')
        self.assertEqual(str(email_no_name), 'a@example.com')


class RecipientTestCase(SimpleTestCase):
    def test_str_method_w_name_and_org(self):
        """Return org (name) when both are set"""
        r = Recipient(email='a@example.com', name='Jim', organization='Org')
        self.assertEqual(str(r), 'Org (Jim)')

    def test_str_method_name_only(self):
        """Return name only when org isn't set"""
        r = Recipient(email='a@example.com', name='Jim', organization='')
        self.assertEqual(str(r), 'Jim')

    def test_str_method_org_only(self):
        """Return org only when name isn't set"""
        r = Recipient(email='a@example.com', name='', organization='An Org')
        self.assertEqual(str(r), 'An Org')

    def test_str_method_no_name_org(self):
        """Return e-mail only when name and org aren't set"""
        r = Recipient(email='a@example.com')
        self.assertEqual(str(r), 'a@example.com')

    @override_settings(FOIATRACKER_ROLODEX_URL='//ex.com')
    def test_rolodex_urls(self):
        """Return Rolodex API endpoint URLs when there are IDs stored"""
        r = Recipient(email='a@example.com', rolodex_contact_id=1,
                      rolodex_person_id=2, rolodex_organization_id=3)
        self.assertEqual(r.rolodex_contact_url, '//ex.com/api/contacts/1/')
        self.assertEqual(r.rolodex_person_url, '//ex.com/api/people/2/')
        self.assertEqual(r.rolodex_organization_url, '//ex.com/api/orgs/3/')

    def test_rolodex_urls_no_ids(self):
        """When there are no Rolodex IDs stored, API URLS should return None"""
        r = Recipient(email='a@example.com')
        self.assertEqual(r.rolodex_person_url, None)
        self.assertEqual(r.rolodex_organization_url, None)
        self.assertEqual(r.rolodex_contact_url, None)

    def test_rolodex_has_match(self):
        """has_rolodex_match should return a boolean indicating whether
        there's a person/org ID on the model"""
        r = Recipient(email='a@example.com')
        self.assertEqual(r.has_rolodex_match(), False)

        r = Recipient(email='a@example.com', rolodex_person_id=1)
        self.assertEqual(r.has_rolodex_match(), True)

        r = Recipient(email='a@example.com', rolodex_organization_id=1)
        self.assertEqual(r.has_rolodex_match(), True)

    @patch('foiatracker.utils.query_rolodex_by_email', return_value=None)
    def test_rolodex_sync_no_match(self, query_rolodex_by_email):
        """When there's no match, blow away all the data we have stored except
        the e-mail address"""
        r = Recipient(email='a@example.com', name='Name', organization='Org')
        r.sync_with_rolodex()
        self.assertEqual(r.email, 'a@example.com')
        self.assertEqual(r.name, '')
        self.assertEqual(r.organization, '')
        self.assertEqual(r.rolodex_person_id, None)
        self.assertEqual(r.rolodex_organization_id, None)
        self.assertEqual(r.rolodex_contact_id, None)

    @patch('foiatracker.utils.query_rolodex_by_email')
    def test_rolodex_sync_email_match_only(self, query_rolodex_by_email):
        """When the email matches but nothing else, store the Rolodex contact
        ID and blow away everything else"""
        query_rolodex_by_email.return_value = {'id': 1, 'person': None,
                                               'org': None}
        r = Recipient(email='a@example.com', name='Name', organization='Org')
        r.sync_with_rolodex()
        self.assertEqual(r.email, 'a@example.com')
        self.assertEqual(r.name, '')
        self.assertEqual(r.organization, '')
        self.assertEqual(r.rolodex_person_id, None)
        self.assertEqual(r.rolodex_organization_id, None)
        self.assertEqual(r.rolodex_contact_id, 1)

    @patch('foiatracker.utils.get_from_rolodex')
    @patch('foiatracker.utils.query_rolodex_by_email')
    def test_rolodex_sync_person_request_error(self, query_rolodex_by_email,
                                               get_from_rolodex):
        """If there's an error requesting person info, blow away person and
        org info and move on"""
        query_rolodex_by_email.return_value = {'id': 1,
                                               'person': '//example.com/5/',
                                               'org': None}
        get_from_rolodex.return_value = None  # Error resposne

        r = Recipient(email='a@example.com', name='Name', organization='Org')
        r.sync_with_rolodex()
        self.assertEqual(r.email, 'a@example.com')
        self.assertEqual(r.name, '')
        self.assertEqual(r.organization, '')
        self.assertEqual(r.rolodex_person_id, None)
        self.assertEqual(r.rolodex_organization_id, None)
        self.assertEqual(r.rolodex_contact_id, 1)

    @patch('foiatracker.utils.get_from_rolodex')
    @patch('foiatracker.utils.query_rolodex_by_email')
    def test_rolodex_sync_person_match(self, query_rolodex_by_email,
                                       get_from_rolodex):
        """If we get a person match, but not a corresponding org then only
        fill in person info and blank out org"""
        query_rolodex_by_email.return_value = {'id': 1,
                                               'person': '//example.com/5/',
                                               'org': None}
        get_from_rolodex.return_value = {
            'firstName': 'Fname',
            'lastName': 'Lname',
            'org_relations': []
        }

        r = Recipient(email='a@example.com', name='Name', organization='Org')
        r.sync_with_rolodex()
        self.assertEqual(r.email, 'a@example.com')
        self.assertEqual(r.name, 'Fname Lname')
        self.assertEqual(r.organization, '')
        self.assertEqual(r.rolodex_person_id, 5)
        self.assertEqual(r.rolodex_organization_id, None)
        self.assertEqual(r.rolodex_contact_id, 1)

    @patch('foiatracker.utils.get_from_rolodex')
    @patch('foiatracker.utils.query_rolodex_by_email')
    def test_rolodex_sync_org_match(self, query_rolodex_by_email,
                                    get_from_rolodex):
        """If we get an org match, fill in org info and blank out person"""
        query_rolodex_by_email.return_value = {'id': 1,
                                               'person': None,
                                               'org': '//example.com/5/'}
        get_from_rolodex.return_value = {
            'orgName': 'An Org'
        }

        r = Recipient(email='a@example.com', name='Name', organization='Org')
        r.sync_with_rolodex()
        self.assertEqual(r.email, 'a@example.com')
        self.assertEqual(r.name, '')
        self.assertEqual(r.organization, 'An Org')
        self.assertEqual(r.rolodex_person_id, None)
        self.assertEqual(r.rolodex_organization_id, 5)
        self.assertEqual(r.rolodex_contact_id, 1)

    @patch('foiatracker.utils.get_from_rolodex')
    @patch('foiatracker.utils.query_rolodex_by_email')
    def test_rolodex_sync_full_match(self, query_rolodex_by_email,
                                     get_from_rolodex):
        """Grab contact, person and org data on a complete match"""
        # Mock initial contact lookup by e-mail
        query_rolodex_by_email.return_value = {'id': 1,
                                               'person': '//example.com/5/',
                                               'org': None}

        # Use side_effect to mock API/helper calls for person info, then org
        get_from_rolodex.side_effect = [{
            'firstName': 'Fname',
            'lastName': 'Lname',
            'org_relations': [
                'http://example.com/3/'
            ]
        }, {
            'orgName': 'Organization'
        }]

        r = Recipient(email='a@example.com', name='Name', organization='Org')
        r.sync_with_rolodex()
        self.assertEqual(r.email, 'a@example.com')
        self.assertEqual(r.name, 'Fname Lname')
        self.assertEqual(r.organization, 'Organization')
        self.assertEqual(r.rolodex_person_id, 5)
        self.assertEqual(r.rolodex_organization_id, 3)
        self.assertEqual(r.rolodex_contact_id, 1)


class InboundEmailTestCase(SimpleTestCase):
    def test_str_method(self):
        """Return the email's subject line when it's stringified"""
        s = Sender(email='a@example.com')
        email = InboundEmail(
            raw='a',
            text='b',
            html='c',
            sender=s,
            sent=timezone.now(),
            subject='Subject line'
        )
        self.assertEqual(str(email), 'Subject line')

    def test_str_method_with_unicode(self):
        """Handle special characters in e-mail subject lines"""
        s = Sender(email='a@example.com')
        email = InboundEmail(
            raw='a',
            text='b',
            html='c',
            sender=s,
            sent=timezone.now(),
            subject='🖕 unicode'
        )
        self.assertEqual(str(email), '🖕 unicode')


@override_settings(ROOT_URLCONF='foiatracker.urls',
                   MAILGUN_API_KEY=None)
class InboundWebHookTestCase(TestCase):
    multi_db = True

    @classmethod
    def setUpClass(cls):
        """Disable post_save signals during this test case"""
        post_save.disconnect(foia_to_slack, sender=Foia,
                             dispatch_uid="foiatracker_slack")
        pre_save.disconnect(hydrate_from_rolodex,
                            dispatch_uid="hydrate_from_rolodex",
                            sender=Recipient)
        pre_save.disconnect(hydrate_from_staff_api,
                            dispatch_uid="hydrate_from_staff_api",
                            sender=Sender)

        fixture_path = os.path.join(os.path.dirname(__file__),
                                    'fixtures/mailgun-post.json')
        with open(fixture_path, 'r') as f:
            cls.mailgun_fixture = json.loads(f.read())
        super(InboundWebHookTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """Re-enable post_save signals after test case"""
        post_save.connect(foia_to_slack, sender=Foia,
                          dispatch_uid="foiatracker_slack")
        pre_save.connect(hydrate_from_rolodex,
                         dispatch_uid="hydrate_from_rolodex",
                         sender=Recipient)
        pre_save.connect(hydrate_from_staff_api,
                         dispatch_uid="hydrate_from_staff_api",
                         sender=Sender)
        super(InboundWebHookTestCase, cls).tearDownClass()

    def test_mailgun_post(self):
        """Stored fixture should result in 1 InboundEmail, 1 Sender and 1
        Recipient saved by ORM"""
        resp = self.client.post('/mailhook/', self.mailgun_fixture)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(InboundEmail.objects.count(), 1)
        self.assertEqual(Sender.objects.count(), 1)
        self.assertEqual(Recipient.objects.count(), 1)

    def test_post_only(self):
        """Non-POST requests should return a 405 Method Not Allowed"""
        resp = self.client.get('/mailhook/')
        self.assertEqual(resp.status_code, 405)

    @override_settings(MAILGUN_INBOUND_TOKEN='token')
    def test_key_auth_valid(self):
        """The included signature/timestamp/token combo should validate agaisnt
        our API key"""
        resp = self.client.post('/mailhook/', self.mailgun_fixture)
        self.assertEqual(resp.status_code, 200)

    @override_settings(MAILGUN_INBOUND_TOKEN='token')
    def test_key_auth_invalid(self):
        """The included signature/timestamp/token combo should validate agaisnt
        our API key"""
        fixture_with_bad_token = self.mailgun_fixture
        fixture_with_bad_token['token'] = 'not-a-good-token'

        resp = self.client.post('/mailhook/', fixture_with_bad_token)
        self.assertEqual(resp.status_code, 200)

    def test_empty_post(self):
        """Empty POST requests should return a 400 Bad Request"""
        resp = self.client.post('/mailhook/', {})
        self.assertEqual(resp.status_code, 400)

    def test_undisclosed_recipients(self):
        """Don't fail when parsing 'To' addresses without @s"""
        undisclosed_fixture = self.mailgun_fixture.copy()
        undisclosed_fixture['To'] = 'undisclosed-recipients:;'
        resp = self.client.post('/mailhook/', undisclosed_fixture)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(InboundEmail.objects.count(), 1)
        self.assertEqual(Sender.objects.count(), 1)
        self.assertEqual(Recipient.objects.count(), 0)


@override_settings(SLACK_TOKEN='slack-token', CELERY_TASK_ALWAYS_EAGER=True)
class SlackMsgTestCase(TestCase):
    multi_db = True

    @classmethod
    def setUpClass(cls):
        """Disable post_save signals during this test case"""
        pre_save.disconnect(hydrate_from_rolodex,
                            dispatch_uid="hydrate_from_rolodex",
                            sender=Recipient)
        pre_save.disconnect(hydrate_from_staff_api,
                            dispatch_uid="hydrate_from_staff_api",
                            sender=Sender)
        super(SlackMsgTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """Re-enable post_save signals after test case"""
        pre_save.connect(hydrate_from_rolodex,
                         dispatch_uid="hydrate_from_rolodex",
                         sender=Recipient)
        pre_save.connect(hydrate_from_staff_api,
                         dispatch_uid="hydrate_from_staff_api",
                         sender=Sender)
        super(SlackMsgTestCase, cls).tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.sender = Sender.objects.create(first_name='First',
                                           last_name='Last',
                                           email='a@example.com')
        cls.email = InboundEmail.objects.create(sender=cls.sender,
                                                sent=timezone.now(),
                                                raw='a', text='b', html='c')
        cls.recipient = Recipient.objects.create(
            name='Re',
            email='r@example.com'
        )
        cls.email.recipients.add(cls.recipient)
        cls.email.save()

    def foia_factory(self):
        foia = Foia.objects.create(
            email=self.email,
            sent=timezone.now(),
            request_subject='Subject line'
        )
        foia.recipients.add(self.recipient)
        foia.save()
        return foia

    def test_get_slack(self):
        """get_slack should return an instance of Slacker"""
        self.assertIsInstance(get_slack(), Slacker)

    def test_get_slack_no_api_key(self):
        """get_slack should raise an ImproperlyConfigured error if SLACK_TOKEN
        is not set"""
        del settings.SLACK_TOKEN
        with self.assertRaises(ImproperlyConfigured):
            get_slack()
        settings.SLACK_TOKEN = 'slack-token'

    @patch('foiatracker.tasks.cache.get', return_value='slackteam')
    @patch('foiatracker.tasks.get_slack')
    @patch('foiatracker.tasks.get_slack_user')
    def test_slack_signal_w_author_info(self, get_slack_user, get_slack,
                                        get_slack_team):
        """Post a Slack message when a Foia is saved, adding Slack author info
        if there's a matching Slack user"""
        # Fake our call to get_slack_user()
        get_slack_user.return_value = 'username', '//example.com/photo.png'

        # Create a model instance, so we can ensure Slack is hit
        self.foia_factory()

        # Assert that post_message was called once
        self.assertEqual(
            get_slack.return_value.chat.post_message.call_count, 1)

        # Assert that the author_link and author_name were built correctly
        kw_args = get_slack.return_value.chat.post_message.call_args_list[0][1]
        self.assertEqual(
            kw_args['attachments'][0]['author_link'],
            'https://slackteam.slack.com/team/username'
        )
        self.assertEqual(kw_args['attachments'][0]['author_name'],
                         'First Last')

    @patch('foiatracker.tasks.get_slack')
    @patch('foiatracker.tasks.get_slack_user', return_value=(None, None))
    def test_slack_signal_no_author_info(self, get_slack_user, get_slack):
        """Post a Slack message when a Foia is saved, skipping the author
        fields if there's no matching Slack user"""
        # Fake our call to get_slack_user()
        get_slack_user.return_value = None, None

        # Create a model instance, so we can ensure Slack is hit
        self.foia_factory()

        # Assert that post_message was called once
        self.assertEqual(
            get_slack.return_value.chat.post_message.call_count, 1)

        # Ensure that no author information was sent
        kw_args = get_slack.return_value.chat.post_message.call_args_list[0][1]
        with self.assertRaises(KeyError):
            kw_args['attachments'][0]['author_link']

    @patch('foiatracker.tasks.get_slack')
    @patch('foiatracker.tasks.cache')
    def test_get_slack_user(self, cache, get_slack):
        """get_slack_user should find matching user w/in Slack API response
        and return username, image or None if not found"""
        # Mock our Slack API response
        class SlackResponse(object):
            body = {
                'members': [{
                    'name': 'Name',
                    'profile': {
                        'email': 'a@example.com',
                        'image_24': 'image.png'
                    }
                }]
            }
        cache.get_or_set.return_value = SlackResponse()

        user_email, user_img = get_slack_user('a@example.com')
        self.assertEqual(user_email, 'Name')
        self.assertEqual(user_img, 'image.png')

        user_email, user_img = get_slack_user('does-not-exist@example.com')
        self.assertEqual(user_email, None)
        self.assertEqual(user_img, None)

    @patch('foiatracker.tasks.get_slack')
    @patch('foiatracker.tasks.get_slack_user', return_value=(None, None))
    def test_foia_update(self, get_slack_user, get_slack):
        """Don't re-send messages for existing Foias"""
        foia = self.foia_factory()
        self.assertEqual(
            get_slack.return_value.chat.post_message.call_count, 1)

        foia.refresh_from_db()
        foia.name = 'New name'
        foia.save()
        self.assertEqual(
            get_slack.return_value.chat.post_message.call_count, 1)

    @patch('foiatracker.tasks.get_slack')
    @patch('foiatracker.tasks.get_slack_user', return_value=(None, None))
    def test_foia_no_recipients(self, get_slack_user, get_slack):
        """Delay sending until recipients are set"""
        # Create an e-mail w/o recipients
        email = InboundEmail.objects.create(sender=self.sender,
                                            sent=timezone.now(), raw='',
                                            text='', html='')

        Foia.objects.create(
            email=email,
            sent=timezone.now(),
            request_subject='Subject line'
        )
        self.assertEqual(
            get_slack.return_value.chat.post_message.call_count, 0)


class UtilsTestCase(TestCase):
    mock_response = [{
        'contact': 'a@example.com'
    }, {
        'contact': 'b@example.com'
    }]

    @classmethod
    def setUpClass(cls):
        """Disable post_save signals during this test case"""
        pre_save.disconnect(hydrate_from_staff_api,
                            dispatch_uid="hydrate_from_staff_api",
                            sender=Sender)
        super(UtilsTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """Re-enable post_save signals after test case"""
        pre_save.connect(hydrate_from_staff_api,
                         dispatch_uid="hydrate_from_staff_api",
                         sender=Sender)
        super(UtilsTestCase, cls).tearDownClass()

    def test_find_contact_by_email(self):
        """Given an e-mail match it with a contact from a Rolodex API
        response, returning None if there's no match"""
        self.assertEqual(
            find_contact_by_email(self.mock_response, 'c@example.com'), None)
        self.assertEqual(
            find_contact_by_email(self.mock_response, 'a@example.com'),
            self.mock_response[0])

    @patch('foiatracker.utils.requests')
    def test_get_from_rolodex(self, requests):
        """Requests to the Rolodex API should return None when HTTP error
        occurs, parsed JSON otherwise"""
        requests.return_value.status_code = 500
        self.assertEqual(get_from_rolodex('http://example.com'), None)

        requests.get.return_value.status_code = requests.codes.ok = 200
        requests.get.return_value.json.return_value = 'json'
        self.assertEqual(get_from_rolodex('http://example.com'), 'json')

    def test_get_id_from_rolodex_url(self):
        """Pop the ID of the back of a Rolodex API URL and return it"""
        self.assertEqual(
            get_id_from_rolodex_url('http://example.com/5/'), 5)

    @patch('foiatracker.utils.requests')
    def test_query_rolodex_by_email(self, requests):
        """Match the passed e-mail with a contact from the Rolodex API"""
        requests.get.return_value.status_code = requests.codes.ok = 200
        requests.get.return_value.json.return_value = self.mock_response
        self.assertEqual(
            query_rolodex_by_email('a@example.com'),
            self.mock_response[0]
        )

    def test_get_by_email_existing(self):
        """Helper should return existing sender by e-mail address"""
        sender = Sender(email='a@example.com', first_name='First',
                        last_name='Last')
        sender.save()

        fetched = get_model_by_email(Sender, 'a@example.com')
        self.assertEqual(sender, fetched)

    def test_get_by_email_new(self):
        """Helper should create new sender when passed e-mail doesn't match"""
        fetched = get_model_by_email(Sender, 'b@example.com')
        self.assertEqual(fetched.email, 'b@example.com')

    def test_get_by_email_new_no_name(self):
        """Helper should create new sender when e-mail doesn't match, changing
        None to '' """
        fetched = get_model_by_email(Sender, 'c@example.com')
        self.assertEqual(fetched.email, 'c@example.com')

    def test_tz_aware_date(self):
        """Helper should convert naive dates to timezone-aware, leave aware
        ones unchanged"""
        naive_date = datetime.datetime.now()
        self.assertTrue(timezone.is_aware(tz_aware_date(naive_date)))
        aware_date = timezone.now()
        self.assertTrue(timezone.is_aware(tz_aware_date(aware_date)))


class SyncCommandTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        """Disable post_save signals during this test case"""
        pre_save.disconnect(hydrate_from_rolodex,
                            dispatch_uid="hydrate_from_rolodex",
                            sender=Recipient)
        super(SyncCommandTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """Re-enable post_save signals after test case"""
        pre_save.connect(hydrate_from_rolodex,
                         dispatch_uid="hydrate_from_rolodex",
                         sender=Recipient)
        super(SyncCommandTestCase, cls).tearDownClass()

    def test_command_output(self):
        """Ensure that recipients are being synced when we call our management
        command"""
        Recipient.objects.create(email='a@example.com')
        Recipient.objects.create(email='b@example.com')

        out = StringIO()
        call_command('rolodexsync', stdout=out)

        self.assertIn('Syncing "a@example.com"', out.getvalue())
        self.assertIn('Syncing "b@example.com"', out.getvalue())
        self.assertIn('Finished syncing recipient information', out.getvalue())
