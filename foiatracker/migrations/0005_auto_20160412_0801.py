# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-04-12 13:01


from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0004_event_date_override'),
    ]

    operations = [
        migrations.RenameField(
            model_name='event',
            old_name='date_override',
            new_name='update_date',
        ),
    ]
