# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-04-06 21:53


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('foiatracker', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='status',
            field=models.CharField(choices=[('kicked', 'Kicked to attorney general'), ('denied', 'Denied by attorney general'), ('relatg', 'Released by attorney general'), ('relagc', 'Released by agency')], max_length=6),
        ),
    ]