# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-04-13 19:52


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0008_auto_20160413_1450'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='foia',
            name='reminder_days',
        ),
        migrations.AddField(
            model_name='foia',
            name='reminder_scheduled_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
