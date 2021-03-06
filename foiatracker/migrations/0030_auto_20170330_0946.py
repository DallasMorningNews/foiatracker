# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-03-30 14:46


from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0029_auto_20170328_1505'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='event',
            options={'ordering': ['-update_date', '-created_at']},
        ),
        migrations.AlterModelOptions(
            name='foia',
            options={'ordering': ['-sent', '-created_at'], 'verbose_name': 'FOIA', 'verbose_name_plural': 'FOIAs'},
        ),
        migrations.AddField(
            model_name='event',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='foia',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
