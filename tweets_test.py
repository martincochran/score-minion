#!/usr/bin/env python
#
# Copyright 2014 Martin Cochran
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import datetime
import json
import unittest

import test_env_setup

test_env_setup.SetUpAppEngineSysPath()

from google.appengine.ext import testbed
from google.appengine.ext import ndb

import tweets

TWEET_JSON_LINES = [
    '{"created_at":"Wed Dec 10 21:00:24 +0000 2014",',
    '"id":542785926674399232,',
    '"id_str":"542785926674399232",',
    '"text":"I took @TheAtlantic\'s Do You Know Where Your Federal Tax Dollars',
    'Go? and it says I am a Rising Superstar (8\/11). http:\/\/t.co\/ub2EMDIssE",',
    '"source":"<a href=\\"http:\/\/twitter.com\/download\/android\\"',
    'rel=\\"nofollow\\">Twitter for Android<\/a>",',
    '"truncated":false,',
    '"in_reply_to_status_id":null,',
    '"in_reply_to_status_id_str":null,',
    '"in_reply_to_user_id":null,',
    '"in_reply_to_user_id_str":null,',
    '"in_reply_to_screen_name":null,',
    '"user":{"id":568757027,'
        '"id_str":"568757027",',
        '"name":"Martin Cochran",',
        '"screen_name":"martin_cochran",',
        '"location":"San Francisco",',
        '"profile_location":null,',
        '"description":"Software engineer, ultimate frisbee player.",',
        '"url":null,',
        '"entities":{"description":{"urls":[]}},',
        '"protected":false,',
        '"followers_count":196,',
        '"friends_count":161,',
        '"listed_count":10,',
        '"created_at":"Wed May 02 03:21:39 +0000 2012",',
        '"favourites_count":35,',
        '"utc_offset":null,',
        '"time_zone":null,',
        '"geo_enabled":true,',
        '"verified":false,',
        '"statuses_count":644,',
        '"lang":"en",',
        '"contributors_enabled":false,',
        '"is_translator":false,',
        '"is_translation_enabled":false,',
        '"profile_background_color":"C0DEED",',
        '"profile_background_image_url":"http:\/\/abs.twimg.com\/images\/themes\/theme1\/bg.png",',
        '"profile_background_image_url_https":"https:\/\/abs.twimg.com\/images\/themes\/theme1\/bg.png",',
        '"profile_background_tile":false,',
        '"profile_image_url":"http:\/\/pbs.twimg.com\/profile_images\/463701621063430145\/CuUrb1aU_normal.png",',
        '"profile_image_url_https":"https:\/\/pbs.twimg.com\/profile_images\/463701621063430145\/CuUrb1aU_normal.png",',
        '"profile_banner_url":"https:\/\/pbs.twimg.com\/profile_banners\/568757027\/1402536259",',
        '"profile_link_color":"0084B4",'
        '"profile_sidebar_border_color":"C0DEED",',
        '"profile_sidebar_fill_color":"DDEEF6",',
        '"profile_text_color":"333333",',
        '"profile_use_background_image":true,',
        '"default_profile":true,',
        '"default_profile_image":false,',
        '"following":null,',
        '"follow_request_sent":null,',
        '"notifications":null},'
    '"geo":{"type":"Point","coordinates":[38.733081,-109.592514]},',
    '"coordinates":null,',
    '"place":{"id":"5a110d312052166f"},',
    '"contributors":null,',
    '"retweet_count":0,',
    '"favorite_count":0,',
    '"entities":{',
      '"hashtags":[{"text":"projectloon","indices":[92,104]}],',
      '"symbols":[],',
        '"user_mentions":[{"screen_name":"TheAtlantic","name":"The Atlantic",',
            '"id":35773039,"id_str":"35773039","indices":[7,19]}],',
        '"media": [{"indices": [39, 61], "type": "photo", "id": 548218214254002177,',
            '"media_url": "http://pbs.twimg.com/media/B5upj7ACQAEb_3u.jpg",',
            '"id_str": "548218214254002177",',
            '"url": "http://t.co/IUWsg3Lp2v",',
            '"media_url_https": "https://pbs.twimg.com/media/B5upj7ACQAEb_3u.jpg",',
            '"sizes": {"small": {"h": 340, "resize": "fit", "w": 340},',
            '"large": {"h": 792, "resize": "fit", "w": 792},',
            '"medium": {"h": 600, "resize": "fit", "w": 600},',
            '"thumb": {"h": 150, "resize": "crop", "w": 150}},',
            '"expanded_url": "http://twitter.com/furyultimate/status/548218220201517057/photo/1",',
            '"display_url": "pic.twitter.com/IUWsg3Lp2v"}],',
        '"urls":[{"url":"http:\/\/t.co\/ub2EMDIssE",',
           '"expanded_url":"http:\/\/m.theatlantic.com\/politics\/archive\/2014\/12\/quiz-how-much-do-you-know-about-the-federal-budget\/383013\/",',
           '"display_url":"m.theatlantic.com\/politics\/archi...","indices":[113,135]}]},',
    '"favorited":false,',
    '"retweeted":false,',
    '"possibly_sensitive":false,',
    '"lang":"en"}']

class TweetTest(unittest.TestCase):

  def setUp(self):
    """Stub out the datastore so we can test it."""
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()

  def testParseTweet(self):
    """Test parsing an example tweet with some basic info."""
    json_str = ''.join(TWEET_JSON_LINES)
    twt = tweets.Tweet.fromJson(json.loads(json_str))

    self.assertEqual('542785926674399232', twt.id_str)
    self.assertTrue(twt.text.find('Your Federal Tax Dollars') != -1)
    self.assertEqual(twt.in_reply_to_status_id, None)
    self.assertEqual(twt.in_reply_to_user_id, None)
    self.assertTrue(twt.source.find('Twitter for Android') != -1)
    self.assertEqual(datetime.datetime(2014, 12, 10, 21, 0, 24), twt.created_at)

    self.assertEqual('568757027', twt.author_id)
    self.assertEqual('martin_cochran', twt.author_screen_name)
    self.assertTrue(ndb.GeoPt(38.733081, -109.592514), twt.geo)
    self.assertEqual('5a110d312052166f', twt.place_id)
    self.assertEqual(0, twt.retweet_count)
    self.assertEqual(0, twt.favorite_count)

    # Entities
    hashtags = twt.entities.hashtags
    self.assertEqual(1, len(hashtags))
    self.assertEqual('projectloon', hashtags[0].text)
    self.assertEqual(92, hashtags[0].start_idx)
    self.assertEqual(104, hashtags[0].end_idx)

    urls = twt.entities.url_mentions
    self.assertEqual(1, len(urls))
    self.assertTrue(urls[0].url.find('ub2EMDIssE') != -1)
    self.assertTrue(urls[0].display_url.find('archi...') != -1)
    self.assertTrue(urls[0].expanded_url.find('quiz-how-much-do-you-know') != -1)
    self.assertEqual(113, urls[0].start_idx)
    self.assertEqual(135, urls[0].end_idx)

    user_mentions = twt.entities.user_mentions
    self.assertEqual(1, len(user_mentions))
    self.assertEqual('35773039', user_mentions[0].user_id)
    self.assertEqual(7, user_mentions[0].start_idx)
    self.assertEqual(19, user_mentions[0].end_idx)

    media = twt.entities.media
    self.assertEqual(1, len(media))
    self.assertEqual('548218214254002177', media[0].id_str)
    self.assertEqual('https://pbs.twimg.com/media/B5upj7ACQAEb_3u.jpg',
        media[0].url_https)
    self.assertEqual(39, media[0].start_idx)
    self.assertEqual(61, media[0].end_idx)

    integers = twt.entities.integers
    self.assertEqual(2, len(integers))
    self.assertEqual(8, integers[0].num)
    self.assertEqual(105, integers[0].start_idx)
    self.assertEqual(106, integers[0].end_idx)

    self.assertEqual(11, integers[1].num)
    self.assertEqual(107, integers[1].start_idx)
    self.assertEqual(109, integers[1].end_idx)

    self.assertEqual('en', twt.lang)

    # Verify the data can be written to the datastore
    twt.put()

  def testParseUser(self):
    """Test parsing an example user with some basic info."""
    json_str = ''.join(TWEET_JSON_LINES)
    user = tweets.User.fromJson(json.loads(json_str).get('user'))

    self.assertEqual('568757027', user.id_str)
    self.assertEqual('Martin Cochran', user.name)
    self.assertEqual('martin_cochran', user.screen_name)

    self.assertEqual('San Francisco', user.location)
    self.assertEqual('Software engineer, ultimate frisbee player.',
        user.description)
    self.assertEqual(None, user.url)
    self.assertEqual(datetime.datetime(2012, 5, 2, 3, 21, 39), user.created_at)

    self.assertFalse(user.protected)
    self.assertEqual(35, user.favourites_count)
    self.assertEqual(None, user.utc_offset)
    self.assertEqual(None, user.time_zone)
    self.assertTrue(user.geo_enabled)
    self.assertFalse(user.verified)
    self.assertEqual(644, user.statuses_count)
    self.assertEqual('en', user.lang)
    self.assertEqual(161, user.friends_count)
    self.assertEqual(196, user.followers_count)
    self.assertTrue(user.profile_image_url_https.find('463701621063430145') != -1)
    self.assertTrue(user.profile_banner_url_https.find('1402536259') != -1)

    # Verify the data can be written to the datastore
    user.put()

  def testParseUser_missingIdStr(self):
    """Test parsing an example user with no id_str field."""
    json_str = '{"user": {}}'
    user = tweets.User.fromJson(json.loads(json_str))

    self.assertEqual(None, user)

  def testParseTweet_missingIdStr(self):
    """Test parsing an example user with no id_str field."""
    json_str = '{}'
    user = tweets.Tweet.fromJson(json.loads(json_str))

    self.assertEqual(None, user)

  def testDateParsing(self):
    data_str = ''
    dt = tweets.ParseTweetDateString(data_str)

    # On a badly parsed tweet, datetime.now() is returned.  Here we give a 10
    # minute buffer to avoid test flakiness.
    self.assertTrue((datetime.datetime.now() - dt) < datetime.timedelta(0, 600, 0))

    data_str = 'bad date string'
    dt = tweets.ParseTweetDateString(data_str)
    self.assertTrue((datetime.datetime.now() - dt) < datetime.timedelta(0, 600, 0))
    
    data_str = 'Wed May 02 03:21:39 +0000 2012'
    dt = tweets.ParseTweetDateString(data_str)
    self.assertEqual(datetime.datetime(2012, 5, 2, 3, 21, 39), dt)

  def testParseGeoData(self):
    geo_obj = None
    self.assertEqual(None, tweets.ParseGeoData(geo_obj))

    geo_obj = {}
    self.assertEqual(None, tweets.ParseGeoData(geo_obj))

    geo_obj = {'type': 'Not point'}
    self.assertEqual(None, tweets.ParseGeoData(geo_obj))

    geo_obj = {'type': 'Point', 'coordinates':[1]}
    self.assertEqual(None, tweets.ParseGeoData(geo_obj))

    geo_obj = {'type': 'Point', 'coordinates': None}
    self.assertEqual(None, tweets.ParseGeoData(geo_obj))

    geo_obj = {'type': 'Point', 'coordinates': [1, 2]}
    self.assertEqual(ndb.GeoPt(1, 2), tweets.ParseGeoData(geo_obj))

  def testParsePlaceId(self):
    place = None
    self.assertEqual(None, tweets.ParsePlaceId(place))

    place = {}
    self.assertEqual(None, tweets.ParsePlaceId(place))

    place = {'id': ''}
    self.assertEqual('', tweets.ParsePlaceId(place))

    place = {'id': 'a'}
    self.assertEqual('a', tweets.ParsePlaceId(place))

  def testParseIntegersInTweet(self):
    entities = tweets.Entities()
    text = '1.7k'

    ies = tweets.ParseIntegersFromTweet(entities, text)
    self.assertFalse(ies)

    text = '7,000'
    entities = tweets.Entities()
    ies = tweets.ParseIntegersFromTweet(entities, text)
    self.assertFalse(ies)

    text = '$500'
    entities = tweets.Entities()
    ies = tweets.ParseIntegersFromTweet(entities, text)
    self.assertFalse(ies)

    text = '3:45'
    entities = tweets.Entities()
    ies = tweets.ParseIntegersFromTweet(entities, text)
    self.assertFalse(ies)

    text = '8-5'
    entities = tweets.Entities()
    ies = tweets.ParseIntegersFromTweet(entities, text)
    self.assertEquals(2, len(ies))

    text = '5.'
    entities = tweets.Entities()
    ies = tweets.ParseIntegersFromTweet(entities, text)
    self.assertEquals(1, len(ies))

    text = '8,'
    entities = tweets.Entities()
    ies = tweets.ParseIntegersFromTweet(entities, text)
    self.assertEquals(1, len(ies))

    text = '18,'
    entities = tweets.Entities()
    ies = tweets.ParseIntegersFromTweet(entities, text)
    self.assertEquals(1, len(ies))


if __name__ == '__main__':
  unittest.main()
