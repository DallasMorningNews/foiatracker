from django.conf import settings
from django.utils.deconstruct import deconstructible

from storages.backends.s3boto import S3BotoStorage


@deconstructible
class FoiatrackerAttachmentStorage(S3BotoStorage):
    bucket_name = settings.FOIATRACKER_ATTACHMENT_BUCKET
    default_acl = 'private'
    querystring_auth = True
