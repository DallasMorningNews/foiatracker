# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-03-23 20:00


from django.db import migrations, models
import foiatracker.custom_storages


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0023_auto_20170323_1445'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailattachment',
            name='stored_file',
            field=models.FileField(storage=foiatracker.custom_storages.FoiatrackerAttachmentStorage(), upload_to='%Y/%m/'),
        ),
    ]
