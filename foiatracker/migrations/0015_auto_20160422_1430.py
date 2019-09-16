# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-04-22 19:30


import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0014_auto_20160422_1246'),
    ]

    operations = [
        migrations.AddField(
            model_name='foia',
            name='recipients',
            field=models.ManyToManyField(to='foiatracker.Recipient'),
        ),
        migrations.AddField(
            model_name='foia',
            name='sent',
            field=models.DateField(default=datetime.date(2016, 4, 22)),
            preserve_default=False,
        ),
    ]
