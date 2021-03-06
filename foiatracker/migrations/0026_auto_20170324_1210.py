# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-03-24 17:10


from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0025_auto_20170324_1124'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='description',
            field=models.TextField(default='description'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='foia',
            name='project',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requests', to='foiatracker.Project'),
        ),
    ]
