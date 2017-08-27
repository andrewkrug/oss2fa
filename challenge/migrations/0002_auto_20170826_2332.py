# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-08-26 23:32
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('challenge', '0001_initial'),
        ('tenants', '0001_initial'),
        ('devices', '0001_initial'),
        ('policy', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='challenge',
            name='binding_context',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='challenge',
                to='tenants.BindingContext'), ),
        migrations.AddField(
            model_name='challenge',
            name='client',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='challenges',
                to='tenants.Client'), ),
        migrations.AddField(
            model_name='challenge',
            name='device',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='challenges',
                to='devices.Device'), ),
        migrations.AddField(
            model_name='challenge',
            name='policy',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='challenges',
                to='policy.Policy'), ),
        migrations.AddIndex(
            model_name='challenge',
            index=models.Index(
                fields=['client'], name='challenge_c_client__f51908_idx'), ),
    ]
