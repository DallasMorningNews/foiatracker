# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-04-12 12:56


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0003_auto_20160411_1653'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='date_override',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]