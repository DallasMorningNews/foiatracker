from datetime import timedelta
import hashlib
import hmac

from django.utils import timezone
from django.conf import settings
from django.utils.timezone import datetime

import holidays
import requests


def tz_aware_date(date):
    """Handle timezone RuntineWarnings by making naive datetimes
    timezone-aware"""
    if timezone.is_naive(date):
        return timezone.make_aware(date)
    return date


def find_contact_by_email(contact_list, email):
    """Go through all of the contacts returned by the API and return the
    first one that matches by e-mail"""
    for contact in contact_list:
        if contact['contact'] == email:
            return contact


def get_from_rolodex(url):
    """Query the API, returning None if there's an error code is returned"""
    r = requests.get(url)

    if r.status_code == requests.codes.ok:
        return r.json()


def get_id_from_rolodex_url(url):
    url_parts = url.split('/')
    return int(url_parts[-2])


def query_rolodex_by_email(email):
    """Using the contacts endpoint, return a matching contact if one exists"""
    url = '%s/api/contacts/' % settings.FOIATRACKER_ROLODEX_URL
    r = requests.get(url)

    if r.status_code == requests.codes.ok:
        return find_contact_by_email(r.json(), email)


def add_business_days(days, from_datetime=datetime.now()):
    """Increment the passed from_date by the passed number of business days
    (excluding weekends and holidays)"""
    try:
        from_datetime.date()
    except AttributeError:
        from_datetime = datetime.combine(from_datetime, datetime.min.time())

    tx_holidays = holidays.US(state='TX')

    while days > 0:
        from_datetime += timedelta(days=1)
        if from_datetime.weekday() >= 5 or from_datetime.date() in tx_holidays:
            continue
        days -= 1
    return from_datetime


def get_model_by_email(ModelClass, email):
    """Return the instance of the @ModelClass that matches @email or create
    and return a new one if one doesn't exist"""
    try:
        model = ModelClass.objects.get(email__iexact=email)
    except ModelClass.DoesNotExist:
        model = ModelClass.objects.create(email=email.lower())

    return model


def verify_mailgun_token(token, timestamp, signature):
    """Verify the passed Mailgun token, using the method at
    https://documentation.mailgun.com/user_manual.html#webhooks. If
    MAILGUN_API_KEY isn't set, returns True for all passed tokens."""
    api_key = getattr(settings, 'MAILGUN_API_KEY', None)
    if api_key is None:
        return True

    expected_signature = hmac.new(key=api_key,
                                  msg='{}{}'.format(timestamp, token),
                                  digestmod=hashlib.sha256).hexdigest()

    return signature == expected_signature
