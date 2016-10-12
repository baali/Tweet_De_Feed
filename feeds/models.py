from __future__ import unicode_literals

from django.db import models
from feeds.mixins import UUIDMixin
# from django.contrib.postgres.fields import JSONField
from django.utils import timezone

# Create your models here.


class AuthToken(UUIDMixin):
    screen_name = models.CharField(max_length=60, unique=True)
    # FIXME: Should they be stored directly?
    access_token = models.CharField(max_length=120)
    access_token_secret = models.CharField(max_length=120)


class TwitterAccount(UUIDMixin):
    screen_name = models.CharField(max_length=60, unique=True)
    followed_from = models.ManyToManyField(AuthToken)
    last_updated = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.screen_name


class TwitterStatus(UUIDMixin):
    tweet_from = models.ForeignKey(TwitterAccount, on_delete=models.CASCADE)
    followed_from = models.ForeignKey(AuthToken, on_delete=models.CASCADE)
    # Now links/urls are excluded from 140 character limit
    status_text = models.CharField(max_length=240)
    status_created = models.DateTimeField()
    status_seen = models.BooleanField(default=False)
    status_url = models.URLField()
    # status_json = JSONField(default={})

    class Meta:
        ordering = ('status_created',)

    def __str__(self):
        return self.tweet_from, self.status_text


class UrlShared(UUIDMixin):
    # Reason I am not storing TwitterStatus is to allow URLs being
    # archived/shared from other sources too(browser-extension etc).
    url = models.URLField(db_index=True)
    shared_from = models.ManyToManyField(TwitterAccount)
    url_shared = models.DateTimeField(default=timezone.now)
    url_seen = models.BooleanField(default=False)
    # tweet_json = JSONField(default={})

    class Meta:
        ordering = ('url_shared',)

    def __str__(self):
        return self.shared_from, self.url
