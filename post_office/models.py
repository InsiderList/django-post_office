import os
from collections import namedtuple
from email.mime.nonmultipart import MIMENonMultipart
from uuid import uuid4

from anymail.message import AnymailMessage
from django.core.exceptions import ValidationError
# from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db import models
from django.utils import timezone
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin
from insiderlist.inbox.mixins import AnymailEmailAbstractModel, \
    EventTypeChoices
from insiderlist.issuers.mixins import IssuerNullableAbstractModel
from insiderlist.utils.models.mixins import CustomAbstractModel
from jsonfield import JSONField
from post_office import cache
from post_office.fields import CommaSeparatedEmailField


from .connections import connections
from .settings import (context_field_class, get_log_level,
                       get_override_recipients, get_template_engine)
from .validators import validate_email_with_name, validate_template_syntax

PRIORITY = namedtuple('PRIORITY', 'low medium high now')._make(range(4))
STATUS = namedtuple('STATUS', 'sent failed queued requeued')._make(
    range(4))


class Email(AnymailEmailAbstractModel, IssuerNullableAbstractModel,
            CustomAbstractModel, TenantModelMixin, models.Model):
    """
    A model to hold email information.
    """
    PRIORITY_CHOICES = [(PRIORITY.low, _("low")),
                        (PRIORITY.medium, _("medium")),
                        (PRIORITY.high, _("high")), (PRIORITY.now, _("now"))]
    STATUS_CHOICES = [(STATUS.sent, _("sent")), (STATUS.failed, _("failed")),
                      (STATUS.queued, _("queued")),
                      (STATUS.requeued, _("requeued"))]

    from_email = models.CharField(_("Email From"), max_length=254,
                                  validators=[validate_email_with_name])
    to = CommaSeparatedEmailField(_("Email To"))
    cc = CommaSeparatedEmailField(_("Cc"))
    bcc = CommaSeparatedEmailField(_("Bcc"))
    subject = models.CharField(_("Subject"), max_length=989, blank=True)
    message = models.TextField(_("Message"), blank=True)
    html_message = models.TextField(_("HTML Message"), blank=True)
    """
    Emails with 'queued' status will get processed by ``send_queued`` command.
    Status field will then be set to ``failed`` or ``sent`` depending on
    whether it's successfully delivered.
    """
    status = models.PositiveSmallIntegerField(
        _("POST_OFFICE status"),
        choices=STATUS_CHOICES, db_index=True,
        blank=True, null=True)
    priority = models.PositiveSmallIntegerField(_("Priority"),
                                                choices=PRIORITY_CHOICES,
                                                blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    last_updated = models.DateTimeField(db_index=True, auto_now=True)
    scheduled_time = models.DateTimeField(_("Scheduled Time"),
                                          blank=True, null=True, db_index=True,
                                          help_text=_(
                                              "The scheduled sending time"))
    expires_at = models.DateTimeField(_("Expires"),
                                      blank=True, null=True,
                                      help_text=_(
                                          "Email won't be sent after this "
                                          "timestamp"))
    number_of_retries = models.PositiveIntegerField(null=True, blank=True)
    headers = JSONField(_('Headers'), blank=True, null=True)
    template = models.ForeignKey('post_office.EmailTemplate', blank=True,
                                 null=True, verbose_name=_("Email template"),
                                 on_delete=models.CASCADE)
    context = context_field_class(_('Context'), blank=True, null=True)
    backend_alias = models.CharField(_("Backend alias"), blank=True,
                                     default='',
                                     max_length=64)

    class Meta(IssuerNullableAbstractModel.Meta):
        app_label = 'post_office'
        verbose_name = pgettext_lazy("Email address", "Email")
        verbose_name_plural = pgettext_lazy("Email addresses", "Emails")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_email_message = None

    def __str__(self):
        return f'Email object {self.pk}'

    def email_message(self):
        """
        Returns Django EmailMessage object for sending.
        """
        if self._cached_email_message:
            return self._cached_email_message

        return self.prepare_email_message()

    def prepare_email_message(self):
        """
        Returns a django ``EmailMessage`` or ``EmailMultiAlternatives`` object,
        depending on whether html_message is empty.
        """
        if get_override_recipients():
            self.to = get_override_recipients()

        if self.template is not None:
            engine = get_template_engine()
            subject = engine.from_string(self.template.subject).render(
                self.context)
            plaintext_message = engine.from_string(
                self.template.content).render(self.context)
            multipart_template = engine.from_string(self.template.html_content)
            html_message = multipart_template.render(self.context)

        else:
            subject = smart_str(self.subject)
            plaintext_message = self.message
            multipart_template = None
            html_message = self.html_message

        connection = connections[self.backend_alias or 'default']
        if isinstance(self.headers, dict) or self.expires_at:
            headers = dict(self.headers or {})
            if self.expires_at:
                headers.update({
                    'Expires': self.expires_at.strftime(
                        "%a, %-d %b %H:%M:%S %z")
                })
        else:
            headers = None

        if html_message:
            if plaintext_message:
                msg = AnymailMessage(
                    subject=subject, body=plaintext_message,
                    from_email=self.from_email,
                    to=self.to, bcc=self.bcc, cc=self.cc,
                    headers=headers, connection=connection)
                msg.attach_alternative(html_message, "text/html")
            else:
                msg = AnymailMessage(
                    subject=subject, body=html_message,
                    from_email=self.from_email,
                    to=self.to, bcc=self.bcc, cc=self.cc,
                    headers=headers, connection=connection)
                msg.content_subtype = 'html'
            if hasattr(multipart_template, 'attach_related'):
                multipart_template.attach_related(msg)

        else:
            msg = AnymailMessage(
                subject=subject, body=plaintext_message,
                from_email=self.from_email,
                to=self.to, bcc=self.bcc, cc=self.cc,
                headers=headers, connection=connection)

        for attachment in self.attachments.all():
            if attachment.headers:
                mime_part = MIMENonMultipart(*attachment.mimetype.split('/'))
                mime_part.set_payload(attachment.file.read())
                for key, val in attachment.headers.items():
                    try:
                        mime_part.replace_header(key, val)
                    except KeyError:
                        mime_part.add_header(key, val)
                msg.attach(mime_part)
            else:
                msg.attach(attachment.name, attachment.file.read(),
                           mimetype=attachment.mimetype or None)
            attachment.file.close()

        self._cached_email_message = msg
        return msg

    def dispatch(self, log_level=None,
                 disconnect_after_delivery=True, commit=True):
        """
        Sends email and log the result.
        """

        try:
            msg = self.email_message()
            msg.send()
            status = STATUS.sent
            message = ''
            exception_type = ''
        except Exception as e:
            msg = None
            status = STATUS.failed
            message = str(e)
            exception_type = type(e).__name__
            self.anymail_logs.create(event_type=EventTypeChoices.REJECTED,
                                     description=f'Exception type: '
                                                 f'{exception_type}, '
                                                 f'Error message: {message}')

            # If run in a bulk sending mode, reraise and let the outer
            # layer handle the exception
            if not commit:
                raise

        if commit:
            self.status = status
            self.save(update_fields=['status'])

            if log_level is None:
                log_level = get_log_level()

            # If log level is 0, log nothing, 1 logs only sending failures
            # and 2 means log both successes and failures
            if log_level == 1:
                if status == STATUS.failed:
                    self.logs.create(status=status, message=message,
                                     exception_type=exception_type)
            elif log_level == 2:
                self.logs.create(status=status, message=message,
                                 exception_type=exception_type)

        if msg:
            from insiderlist.inbox.models import AnymailLog
            anymail_log_list = []
            for key, value in msg.anymail_status.recipients.items():
                eventype_choice = value.status.upper()
                eventtype = EventTypeChoices[eventype_choice]
                anymail_log_obj = AnymailLog(
                    issuer=self.issuer,
                    email=self,
                    recipient=key,
                    message_id=value.message_id,
                    event_type=eventtype,
                    timestamp=timezone.now()
                )
                anymail_log_list.append(anymail_log_obj)
            AnymailLog.objects.bulk_create(anymail_log_list)
            self.anymail_message_id = msg.anymail_status.message_id
            self.save(update_fields=['anymail_message_id'])

        return msg

    def clean(self):
        if self.scheduled_time and self.expires_at and self.scheduled_time > \
                self.expires_at:
            raise ValidationError(_(
                "The scheduled time may not be later than the expires time."))

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Log(IssuerNullableAbstractModel,
          CustomAbstractModel, TenantModelMixin, models.Model):
    """
    A model to record sending email sending activities.
    """

    STATUS_CHOICES = [(STATUS.sent, _("sent")), (STATUS.failed, _("failed"))]

    email = models.ForeignKey(Email, editable=False, related_name='logs',
                              verbose_name=_('Email object'),
                              on_delete=models.CASCADE, null=True)
    date = models.DateTimeField(auto_now_add=True)
    status = models.PositiveSmallIntegerField(_('Status'),
                                              choices=STATUS_CHOICES)
    exception_type = models.CharField(_('Exception type'), max_length=255,
                                      blank=True)
    message = models.TextField(_('Message'))

    class Meta:
        app_label = 'post_office'
        verbose_name = _("POST_OFFICE Log")
        verbose_name_plural = _("POST_OFFICE Logs")
        constraints = IssuerNullableAbstractModel._meta.constraints

    def __str__(self):
        # return str(self.date)
        return 'Log: ' + str(self.pk)


class EmailTemplateManager(TenantManagerMixin,
                           models.Manager):
    def get_by_natural_key(self, name, language, default_template):
        return self.get(name=name, language=language,
                        default_template=default_template)


class EmailTemplate(IssuerNullableAbstractModel, CustomAbstractModel,
                    TenantModelMixin, models.Model):
    """
    Model to hold template information from db
    """
    name = models.CharField(_('Name'), max_length=255,
                            help_text=_("e.g: 'welcome_email'"))
    description = models.TextField(_('Description'), blank=True,
                                   help_text=_(
                                       "Description of this template."))
    created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    subject = models.CharField(max_length=255, blank=True,
                               verbose_name=_("Subject"),
                               validators=[validate_template_syntax])
    content = models.TextField(blank=True,
                               verbose_name=_("Content"),
                               validators=[validate_template_syntax])
    html_content = models.TextField(blank=True,
                                    verbose_name=_("HTML content"),
                                    validators=[validate_template_syntax])
    language = models.CharField(max_length=12,
                                verbose_name=_("Language"),
                                help_text=_(
                                    "Render template in alternative language"),
                                default='', blank=True)
    default_template = models.ForeignKey('self',
                                         related_name='translated_templates',
                                         null=True, default=None,
                                         verbose_name=_('Default template'),
                                         on_delete=models.CASCADE)
    context_variables = JSONField(null=True, blank=True)

    objects = EmailTemplateManager()

    class Meta(IssuerNullableAbstractModel.Meta):
        app_label = 'post_office'
        unique_together = ('name', 'language', 'default_template')
        verbose_name = _("Email Template")
        verbose_name_plural = _("Email Templates")
        ordering = ['name']

    def __str__(self):
        return '%s %s' % (self.name, self.language)

    def natural_key(self):
        return (self.name, self.language, self.default_template)

    def save(self, *args, **kwargs):
        # If template is a translation, use default template's name
        if self.default_template and not self.name:
            self.name = self.default_template.name

        template = super().save(*args, **kwargs)
        cache.delete(self.name)
        return template


def get_upload_path(instance, filename):
    """Overriding to store the original filename"""
    if not instance.name:
        instance.name = filename  # set original filename
    date = timezone.now().date()
    filename = '{name}.{ext}'.format(name=uuid4().hex,
                                     ext=filename.split('.')[-1])

    return os.path.join('post_office_attachments', str(date.year),
                        str(date.month), str(date.day), filename)


class Attachment(IssuerNullableAbstractModel, CustomAbstractModel,
                 TenantModelMixin, models.Model):
    """
    A model describing an email attachment.
    """
    file = models.FileField(_('File'), upload_to=get_upload_path)
    name = models.CharField(_('Name'), max_length=255,
                            help_text=_("The original filename"))
    emails = models.ManyToManyField(Email, related_name='attachments',
                                    verbose_name=_('Emails'))
    mimetype = models.CharField(max_length=255, default='', blank=True)
    headers = JSONField(_('Headers'), blank=True, null=True)

    class Meta(IssuerNullableAbstractModel.Meta):
        app_label = 'post_office'
        verbose_name = _("Attachment")
        verbose_name_plural = _("Attachments")

    def __str__(self):
        return self.name
