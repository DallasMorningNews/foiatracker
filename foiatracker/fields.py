from django.forms import ModelMultipleChoiceField
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from foiatracker.models import Recipient
from foiatracker.utils import get_model_by_email


class RecipientsChoiceField(ModelMultipleChoiceField):
    def pks_from_emails(self, val):
        key = self.to_field_name or 'pk'

        try:
            self.queryset.filter(**{key: val})
            return val
        except (ValueError, TypeError):
            validate_email(val)
            return get_model_by_email(Recipient, val).pk

    def clean(self, value):
        if self.required and not value:
            raise ValidationError(self.error_messages['required'],
                                  code='required')
        elif not self.required and not value:
            return self.queryset.none()
        if not isinstance(value, (list, tuple)):
            raise ValidationError(self.error_messages['list'], code='list')

        # Use our custom logic to create Recipient models for e-mails that
        # don't exist and sync them with Rolodex
        value = [self.pks_from_emails(v) for v in value]

        qs = self._check_values(value)
        self.run_validators(value)
        return qs
