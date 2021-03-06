from django.test import TestCase
import os
import tweepy
from feeds.models import AuthToken, TwitterAccount, TwitterStatus, UrlShared
from feeds.serializers import StatusSerializer, UrlSerializer
import pytz
import datetime


class SerializerTests(TestCase):
    @classmethod
    def setUpClass(cls):
        """.
        """
        cls.oauth_consumer_key = os.environ.get('TWITTER_CONSUMER_KEY', '')
        cls.oauth_consumer_secret = os.environ.get('TWITTER_CONSUMER_SECRET', '')
        cls.oauth_token = os.environ.get('ACCESS_KEY', '')
        cls.oauth_token_secret = os.environ.get('ACCESS_SECRET', '')
        cls.auth = tweepy.OAuthHandler(cls.oauth_consumer_key, cls.oauth_consumer_secret)
        cls.auth.set_access_token(cls.oauth_token, cls.oauth_token_secret)
        cls.api = tweepy.API(cls.auth, wait_on_rate_limit=True)
        cls.me = cls.api.me()
        auth_token, created = AuthToken.objects.get_or_create(screen_name=cls.me.screen_name)
        auth_token.access_token = cls.oauth_token
        auth_token.access_token_secret = cls.oauth_token_secret
        auth_token.save()
        for friend in tweepy.Cursor(cls.api.friends).items():
            if not friend.url:
                continue
            last_updated = pytz.utc.localize(datetime.datetime.now() - datetime.timedelta(days=365))
            twitter_account = TwitterAccount.objects.create(screen_name=friend.screen_name,
                                                            last_updated=last_updated)
            twitter_account.save()
            twitter_account.followed_from.add(auth_token)
            break
        cls.statuses = cls.api.user_timeline(screen_name=friend.screen_name)
        cls.friend_account = twitter_account

    @classmethod
    def tearDownClass(cls):
        pass

    def test_tweets_serializer(self):
        auth_token, created = AuthToken.objects.get_or_create(screen_name=self.me.screen_name)
        for status in self.statuses:
            if getattr(status, 'retweeted_status', None) and status.text.endswith(u'\u2026'):
                text = self.friend_account.screen_name + ' Retweeted ' + status.retweeted_status.author.screen_name + ': ' + status.retweeted_status.text
            else:
                text = status.text
            created = pytz.utc.localize(status.created_at)
            url = 'https://twitter.com/' + self.friend_account.screen_name + '/status/' + status.id_str
            status_obj = TwitterStatus.objects.create(
                tweet_from=self.friend_account,
                followed_from=auth_token,
                status_text=text,
                status_created=created,
                status_url=url)
            status_obj.save()

            serialized_obj = StatusSerializer(status_obj)
            self.assertTrue(serialized_obj.data)
            self.assertEqual(serialized_obj.data['status_text'], text)
            self.assertEqual(serialized_obj.data['status_url'], url)
            self.assertEqual(serialized_obj.data['tweet_from']['screen_name'], self.friend_account.screen_name)
            self.assertEqual(serialized_obj.data['followed_from'], auth_token.uuid)

    def test_links_serializer(self):
        auth_token, created = AuthToken.objects.get_or_create(screen_name=self.me.screen_name)
        for status in self.statuses:
            for url_entity in status._json['entities'].get('urls', []):
                if not url_entity.get('expanded_url', ''):
                    continue
                if len(url_entity['expanded_url']) > 200:
                    continue
                shared_at = pytz.utc.localize(status.created_at)
                link_obj, created = UrlShared.objects.get_or_create(
                    url=url_entity['expanded_url'], defaults={'url_shared': shared_at})
                if created:
                    link_obj.save()
                link_obj.shared_from.add(self.friend_account)
                link_obj.save()
                serialized_obj = UrlSerializer(link_obj)
                self.assertTrue(serialized_obj.data)
                self.assertEqual(serialized_obj.data['url'], url_entity['expanded_url'])
                self.assertEqual(serialized_obj.data['shared_from'][0]['screen_name'], self.friend_account.screen_name)
