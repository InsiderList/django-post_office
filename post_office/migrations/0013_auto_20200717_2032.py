# Generated by Django 3.0.8 on 2020-07-17 19:32

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import django_multitenant.fields


class Migration(migrations.Migration):

    dependencies = [
        ('post_office', '0012_emailtemplate_context_variables'),
    ]

    operations = [
        migrations.AddField(
            model_name='log',
            name='click_url',
            field=models.CharField(blank=True, help_text="For 'clicked' events, the str url the user clicked. Otherwise None.", max_length=255, null=True, verbose_name='Click URL'),
        ),
        migrations.AddField(
            model_name='log',
            name='description',
            field=models.TextField(blank=True, help_text='If available, a str with a (usually) human-readable description of the event. Otherwise None. For example, might explain why an email has bounced. Exact format varies by ESP (and sometimes event type).', null=True, verbose_name='Description'),
        ),
        migrations.AddField(
            model_name='log',
            name='esp_event',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, help_text='The “raw” event data from the ESP, deserialized into a python data structure. For most ESPs this is either parsed JSON (as a dict), or HTTP POST fields (as a Django QueryDict). This gives you (non-portable) access to additional information provided by your ESP. For example, some ESPs include geo-IP location information with open and click events.', null=True, verbose_name='ESP Event'),
        ),
        migrations.AddField(
            model_name='log',
            name='event_dict',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, help_text='Complete dict of the event from the ESP', null=True, verbose_name='event.__dict__'),
        ),
        migrations.AddField(
            model_name='log',
            name='event_id',
            field=models.CharField(blank=True, help_text='A str unique identifier for the event, if available; otherwise None. Can be used to avoid processing the same event twice. Exact format varies by ESP, and not all ESPs provide an event_id for all event types.', max_length=255, null=True, verbose_name='Event ID'),
        ),
        migrations.AddField(
            model_name='log',
            name='event_type',
            field=models.PositiveSmallIntegerField(blank=True, choices=[(0, 'sent'), (1, 'failed'), (2, 'queued'), (3, 'invalid'), (4, 'rejected'), (5, 'bounced'), (6, 'deferred'), (7, 'delivered'), (8, 'autoresponded'), (9, 'opened'), (10, 'clicked'), (11, 'complained'), (12, 'unsubscribed'), (13, 'subscribed'), (14, 'unknown')], help_text='A normalized str identifying the type of tracking event. Also updated on AnymailEmail as recipient_status.', null=True, verbose_name='Event type'),
        ),
        migrations.AddField(
            model_name='log',
            name='metadata',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, help_text='A dict of unique data attached to the message. Will be empty if the ESP doesn’t provide metadata with its tracking events.', null=True, verbose_name='Meta data'),
        ),
        migrations.AddField(
            model_name='log',
            name='mta_response',
            field=models.TextField(blank=True, help_text='If available, a str with a raw (intended for email administrators) response from the receiving MTA. Otherwise None. Often includes SMTP response codes, but the exact format varies by ESP (and sometimes receiving MTA).', null=True, verbose_name='MTA Response'),
        ),
        migrations.AddField(
            model_name='log',
            name='reject_reason',
            field=models.PositiveSmallIntegerField(blank=True, choices=[(0, 'invalid'), (1, 'bounced'), (2, 'timed_out'), (3, 'blocked'), (4, 'spam'), (5, 'rejected'), (6, 'unsubscribed'), (7, 'other'), (8, 'none')], help_text="For bounced' and 'rejected' events, a normalized str giving the reason for the bounce/rejection.", null=True, verbose_name='Reject reason'),
        ),
        migrations.AddField(
            model_name='log',
            name='tags',
            field=models.TextField(blank=True, help_text='A list of str tags attached to the message. Will be empty if the ESP doesn’t provide tags with its tracking events.', null=True, verbose_name='Tags'),
        ),
        migrations.AddField(
            model_name='log',
            name='timestamp',
            field=models.DateTimeField(blank=True, help_text='A datetime indicating when the event was generated. (The timezone is often UTC, but the exact behavior depends on your ESP and account settings. Anymail ensures that this value is an aware datetime with an accurate timezone.)', null=True, verbose_name='Time stamp'),
        ),
        migrations.AddField(
            model_name='log',
            name='user_agent',
            field=models.CharField(blank=True, help_text="For 'opened' and 'clicked' events, a str identifying the browser and/or email client the user is using, if available. Otherwise None.", max_length=255, null=True, verbose_name='User agent'),
        ),
        migrations.AlterField(
            model_name='log',
            name='email',
            field=django_multitenant.fields.TenantForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='post_office.Email', verbose_name='Email address'),
        ),
        migrations.AddConstraint(
            model_name='log',
            constraint=models.CheckConstraint(check=models.Q(event_type__in=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]), name='event_type_choice_anymaillog'),
        ),
        migrations.AddConstraint(
            model_name='log',
            constraint=models.CheckConstraint(check=models.Q(reject_reason__in=[0, 1, 2, 3, 4, 5, 6, 7, 8]), name='reject_reason_choice_anymaillog'),
        ),
    ]
