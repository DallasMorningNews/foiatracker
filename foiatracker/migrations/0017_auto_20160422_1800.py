# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-04-22 23:00


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0016_auto_20160422_1500'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inboundemail',
            name='recipients',
            field=models.ManyToManyField(blank=True, null=True, to='foiatracker.Recipient'),
        ),
    ]
