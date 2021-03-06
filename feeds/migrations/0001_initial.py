# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-10-24 10:12
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AuthToken',
            fields=[
                ('uuid', models.CharField(db_index=True, default=uuid.uuid4, editable=False, max_length=64, primary_key=True, serialize=False)),
                ('screen_name', models.CharField(max_length=60, unique=True)),
                ('access_token', models.CharField(max_length=120)),
                ('access_token_secret', models.CharField(max_length=120)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='TwitterAccount',
            fields=[
                ('uuid', models.CharField(db_index=True, default=uuid.uuid4, editable=False, max_length=64, primary_key=True, serialize=False)),
                ('screen_name', models.CharField(max_length=60, unique=True)),
                ('last_updated', models.DateTimeField(default=django.utils.timezone.now)),
                ('followed_from', models.ManyToManyField(to='feeds.AuthToken')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='TwitterStatus',
            fields=[
                ('uuid', models.CharField(db_index=True, default=uuid.uuid4, editable=False, max_length=64, primary_key=True, serialize=False)),
                ('status_text', models.CharField(max_length=240)),
                ('status_created', models.DateTimeField()),
                ('status_seen', models.BooleanField(default=False)),
                ('status_url', models.URLField(unique=True)),
                ('followed_from', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='feeds.AuthToken')),
                ('tweet_from', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='feeds.TwitterAccount')),
            ],
            options={
                'ordering': ('-status_created',),
            },
        ),
        migrations.CreateModel(
            name='UrlShared',
            fields=[
                ('uuid', models.CharField(db_index=True, default=uuid.uuid4, editable=False, max_length=64, primary_key=True, serialize=False)),
                ('url', models.URLField(db_index=True)),
                ('url_shared', models.DateTimeField(default=django.utils.timezone.now)),
                ('url_seen', models.BooleanField(default=False)),
                ('quoted_text', models.TextField(blank=True)),
                ('shared_from', models.ManyToManyField(to='feeds.TwitterAccount')),
            ],
            options={
                'ordering': ('-url_shared',),
            },
        ),
    ]
