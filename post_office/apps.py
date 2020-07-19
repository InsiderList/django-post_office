from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PostOfficeConfig(AppConfig):
    name = 'post_office'
    verbose_name = _("Post Office")

    def ready(self):
        from actstream import registry
        registry.register(self.get_model('Email'))
        # from post_office.signals import email_queued

        # TODO: This signal causes mail.send() to hang, so disable for
        #  now as it's unusued
        # if hasattr(tasks, 'queued_mail_handler'):
            # email_queued.connect(tasks.queued_mail_handler)
