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

import json
import os
import unittest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()

from google.appengine.ext import testbed

import tweet_util
import tweets

class TweetUtilTest(unittest.TestCase):
  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_user_stub()

  def tearDown(self):
    # Reset the URL stub to the original function
    self.testbed.deactivate()

  def testQueryAndSetTweet(self):
    tweet = tweets.Tweet.fromJson(json.loads(
        '{"user": {"id_str": "2", "screen_name": "bob"}, "id_str": "1"}'))

    tweet_query = tweets.Tweet.query(ancestor=tweets.tweet_key(tweet.id_str))
    twts = tweet_query.fetch(1)
    self.assertFalse(twts)

    tweet_util.QueryAndSetTweet(tweet)
    tweet_query = tweets.Tweet.query(ancestor=tweets.tweet_key(tweet.id_str))
    twts = tweet_query.fetch(1)
    self.assertEqual(1, len(twts))
    self.assertEqual(twts[0], tweet)

    # This will be a different object since the creation date will be different
    new_tweet = tweets.Tweet.fromJson(json.loads(
        '{"user": {"id_str": "2", "screen_name": "bob"}, "id_str": "1"}'))
    returned_tweet = tweet_util.QueryAndSetTweet(new_tweet)

    self.assertEqual(returned_tweet, tweet)
    self.assertFalse(tweet == new_tweet)
    self.assertFalse(returned_tweet == new_tweet)
    
    tweet_query = tweets.Tweet.query(ancestor=tweets.tweet_key(tweet.id_str))
    twts = tweet_query.fetch(1)
    self.assertEqual(1, len(twts))
    self.assertEqual(twts[0], tweet)
