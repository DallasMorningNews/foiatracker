from django.apps import AppConfig


class FoiaTrackerConfig(AppConfig):
    name = 'foiatracker'
    verbose_name = 'FOIA tracker'

    def ready(self):
        import foiatracker.signals  # noqa
