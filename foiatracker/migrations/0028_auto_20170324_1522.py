# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-03-24 20:22


from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0027_project_created_at'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='project',
            options={'ordering': ['-created_at']},
        ),
    ]
