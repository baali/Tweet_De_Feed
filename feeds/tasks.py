import datetime
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, Comment
from xml.dom import minidom
from django.conf import settings
from django.contrib.staticfiles.templatetags.staticfiles import static
from feedgen.feed import FeedGenerator
import pytz
import tweepy
from django.utils import timezone
from feeds.models import AuthToken, TwitterAccount, UrlShared, TwitterStatus
from tweet_d_feed.celery import app


@app.task(bind=True)
def update_feed(self, uuid):
    try:
        auth_token = AuthToken.objects.get(uuid=uuid)
    except AuthToken.DoesNotExist:
        print('Account with uuid', uuid, 'DoesNotExist')
        return
    print('Updating feed for', auth_token.screen_name)
    accounts = TwitterAccount.objects.filter(followed_from__uuid=uuid)
    if not accounts:
        return
    feed_date = datetime.date.today()
    fg = FeedGenerator()
    fg.id('https://twitter.com/%s' % auth_token.screen_name)
    fg.description('Links shared by people you follow')
    fg.title(auth_token.screen_name)
    fg.author({'name': auth_token.screen_name})
    fg.link(href='https://twitter.com/%s' % auth_token.screen_name, rel='alternate')
    fg.language('en')
    print('Parsing links shared by people followed from', auth_token.screen_name)
    for link in UrlShared.objects.filter(shared_from__in=[account.uuid for account in accounts], url_shared__gte=feed_date):
        fe = fg.add_entry()
        fe.id(link.url)
        fe.author({'name': ', '.join([shared_from.screen_name for shared_from in link.shared_from.all()])})
        fe.title(link.url)
        fe.content(link.quoted_text)
        fe.pubdate(link.url_shared)
    print('Dumping links for', auth_token.screen_name, 'in feed file')
    with open('feeds/static/xml/%s-feed.xml' % auth_token.uuid, 'wb') as feed:
        feed.write(fg.atom_str(pretty=True))
    print('Successfully updated feed for', auth_token.screen_name)


@app.task(bind=True)
def update_accounts_task(self, uuid=''):
    try:
        auth_tokens = [AuthToken.objects.get(uuid=uuid)] if uuid else AuthToken.objects.all()
    except AuthToken.DoesNotExist:
        return 'Given account(%s) DoesNotExist' % uuid
    for auth_token in auth_tokens:
        auth = tweepy.OAuthHandler(settings.TWITTER_CONSUMER_KEY,
                                   settings.TWITTER_CONSUMER_SECRET)
        auth.set_access_token(auth_token.access_token,
                              auth_token.access_token_secret)
        try:
            api = tweepy.API(auth, wait_on_rate_limit=True)
        except tweepy.TweepError:
            print('Error! Failed to get access token for user %s.' %
                  auth_token.screen_name)
            continue
        me = api.me()
        friend_count = 0
        for friend in tweepy.Cursor(api.friends).items():
            friend_count += 1
            meta = {'info': 'Processing user %s/<a href="https://twitter.com/%s">%s</a>' % (friend.name, friend.screen_name, friend.screen_name),
                    'count': friend_count,
                    'total': me.friends_count,
                    }
            self.update_state(state='PROGRESS', meta=meta)
            statuses = api.user_timeline(screen_name=friend.screen_name)
            if friend.screen_name is None or friend.name is None:
                continue
            try:
                twitter_account = TwitterAccount.objects.get(screen_name=friend.screen_name)
                if not twitter_account.followed_from.filter(uuid=auth_token.uuid).exists():
                    twitter_account.followed_from.add(auth_token)
            except TwitterAccount.DoesNotExist:
                twitter_account, created = TwitterAccount.objects.get_or_create(screen_name=friend.screen_name,
                                                                                defaults={'last_updated': timezone.now() - datetime.timedelta(days=365)})
                twitter_account.save()
                twitter_account.followed_from.add(auth_token)

            # Check if there were no recent updates in the timeline by the author
            if not [status for status in statuses if status.author.screen_name == friend.screen_name and pytz.utc.localize(status.created_at) > twitter_account.last_updated]:
                continue
            count = 0
            for status in statuses:
                if not status.author.screen_name == friend.screen_name:
                    # skipping tweets where someone else is talking to friend
                    # FIXME: We have to consider case when user 'favourites' a tweet <- They could be treasure trove
                    continue
                if pytz.utc.localize(status.created_at) > twitter_account.last_updated:
                    twitter_account.last_updated = pytz.utc.localize(status.created_at)
                # FIXME: Should we have a different check to avoid duplicate tweets?
                url = 'https://twitter.com/' + twitter_account.screen_name + '/status/' + status.id_str
                count += 1
                if TwitterStatus.objects.filter(status_url=url).exists():
                    continue
                if getattr(status, 'retweeted_status', None) and status.text.endswith(u'\u2026'):
                    text = status.retweeted_status.author.screen_name + ': ' + status.retweeted_status.text
                else:
                    text = status.text
                tweeted_at = pytz.utc.localize(status.created_at)
                status_obj = TwitterStatus(
                    tweet_from=twitter_account,
                    followed_from=auth_token,
                    status_text=text,
                    status_url=url)
                status_obj.status_created = tweeted_at
                status_obj.save()

                # In case of "quoted tweets" the original tweets is part of the url entities
                # FIXME: I have to handle it better, in case quoted tweet has an external link?
                # if status.is_quote_status:
                #     continue
                for url_entity in status._json['entities']['urls']:
                    if url_entity.get('expanded_url', '').startswith('https://twitter.com/i/web/status/'):
                        continue
                    if url_entity.get('expanded_url', ''):
                        link_obj, created = UrlShared.objects.get_or_create(
                            url=url_entity['expanded_url'],
                            quoted_text=text,
                            defaults={'url_shared': pytz.utc.localize(status.created_at)})
                        if created:
                            link_obj.save()
                        if not link_obj.shared_from.filter(uuid=twitter_account.uuid).exists():
                            link_obj.shared_from.add(twitter_account)
                            link_obj.save()
            print('Updated', friend.screen_name, 'Added', count, 'Tweets')
            twitter_account.save()
    return 'Successfully updated accounts.'


@app.task(bind=True)
def opml_task(self, token, verifier, host_uri):
    auth = tweepy.OAuthHandler(
        settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
    auth.request_token = token
    try:
        auth.get_access_token(verifier)
    except tweepy.TweepError:
        raise
    try:
        api = tweepy.API(auth, wait_on_rate_limit=True)
    except tweepy.TweepError:
        raise
    me = api.me()
    auth_token, created = AuthToken.objects.get_or_create(
        screen_name=me.screen_name)
    auth_token.access_token = auth.access_token
    auth_token.access_token_secret = auth.access_token_secret
    auth_token.save()
    root = Element('opml')
    generated_on = str(datetime.datetime.now())
    root.set('version', '1.0')
    root.append(Comment('Feed list of all tweets'))

    head = SubElement(root, 'head')
    title = SubElement(head, 'title')
    title.text = 'My Twitter Feed'
    dc = SubElement(head, 'dateCreated')
    dc.text = generated_on
    dm = SubElement(head, 'dateModified')
    dm.text = generated_on

    body = SubElement(root, 'body')
    count = 0
    for friend in tweepy.Cursor(api.friends).items():
        count += 1
        if not friend.url:
            continue
        if friend.url:
            meta = {'info': 'Processing user %s/<a href="https://twitter.com/%s">%s</a>' % (friend.name, friend.screen_name, friend.screen_name),
                    'count': count,
                    'total': me.friends_count,
                    }
            self.update_state(state='PROGRESS', meta=meta)
            # timeline = friend.timeline()
            # rss_task.apply_async([friend.url, friend.screen_name, friend.name, friend.id_str, timeline])
            SubElement(body, 'outline',
                       {'text': friend.name,
                        'title': friend.name,
                        'type': 'rss',
                        'htmlUrl': friend.url,
                        'xmlUrl': host_uri + static('xml/feed-%s.xml' % friend.screen_name),
                        })

            # XXX: Rate limiting(??)
            last_updated = pytz.utc.localize(
                datetime.datetime.now() - datetime.timedelta(days=365))
            try:
                twitter_account = TwitterAccount.objects.create(
                    screen_name=friend.screen_name, followed_from=auth_token, last_updated=last_updated)
                twitter_account.save()
            except:
                print('Skipping friend %s for now' % friend.screen_name)
    with open('feeds/static/opml/%s.opml' % me.screen_name, 'w') as opml:
        rough_string = ElementTree.tostring(root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        opml.write(reparsed.toprettyxml(indent="  ").encode('utf8'))
    api.send_direct_message(screen_name=me.screen_name,
                            text='''Hey there! We just finished compiling OPML file of the RSS feed
based on people you follow. You can access it here
%s Use this file with any feed
reader of you choice.''' % (host_uri + static('opml/' + me.screen_name + '.opml')))
    return host_uri + static('opml/' + me.screen_name + '.opml')
