# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-04-11 16:16


from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0031_auto_20170403_1223'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailattachment',
            name='email',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='foiatracker.InboundEmail'),
        ),
    ]
