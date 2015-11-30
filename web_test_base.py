#!/usr/bin/env python
#
# Copyright 2015 Martin Cochran
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
import logging
import unittest

from google.appengine.api import taskqueue
from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_service_pb
from google.appengine.api import urlfetch_stub
from google.appengine.ext import testbed

import game_model
import tweets


class WebTestError(Exception):
  pass


class WebTestBase(unittest.TestCase):
  """Base test class for testbed tests with some common functionality."""
  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_taskqueue_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_urlfetch_stub()
    self.testbed.init_user_stub()

    # Stub out the request / response for the Twitter API
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      response.set_statuscode(self.return_statuscode.pop(0))
      response.set_content(self.return_content.pop(0))

    self.url_fetch_stub = self.testbed.get_stub(testbed.URLFETCH_SERVICE_NAME)
    self.saved_retrieve_url = self.url_fetch_stub._RetrieveURL
    self.url_fetch_stub._RetrieveURL = _FakeFetch
    self.taskqueue_stub = self.testbed.get_stub(testbed.TASKQUEUE_SERVICE_NAME)

    self.SetTimelineResponse(self.CreateTweet(1, ('bob', 1234)))

  def tearDown(self):
    # Reset the URL stub to the original function
    self.url_fetch_stub._RetrieveURL = self.saved_retrieve_url
    self.testbed.deactivate()

  @classmethod
  def CreateTweet(cls, id_str, user_screen_name_and_id, text='',
      created_at=None, list_id=None):
    """Convience method to create a Tweet object with minimal required fields.
    
    Args:
      id_str: id of tweet
      user_screen_name_and_id: Pair of screen_name and id_str of user
      text: Text of tweet.
      created_at: datetime of when Tweet was created.
      list_id: List ID this was tweet was crawled from.
    Returns:
      A Tweet object with these required fields.
    """
    d = {}
    d['user'] = {
        'id_str': str(user_screen_name_and_id[1]),
        'id': long(user_screen_name_and_id[1]),
        'screen_name': user_screen_name_and_id[0]
    }
    d['id_str'] = str(id_str)
    d['id'] = long(id_str)
    d['text'] = text
    if created_at:
      d['created_at'] = tweets.WriteTweetDateString(created_at)

    logging.debug('Created json object: %s', d)
    # We re-use the Tweet parser because it sets all the default fields correctly.
    return tweets.Tweet.fromJson(d, from_list=list_id)

  @classmethod
  def CreateUser(cls, id, screen_name, created_at=None, profile_url_https=''):
    """Convience method to create a User object with minimal required fields.
    
    Args:
      id: (integer) id of user
      screen_name: screen_name of user
      created_at: datetime of when User was created.
      profile_url_https: https URL of profile image
    Returns:
      A User object with these required fields.
    """
    d = {}
    d['id_str'] = str(id)
    d['id'] = id
    d['screen_name'] = screen_name
    if created_at:
      d['created_at'] = tweets.WriteTweetDateString(created_at)
    if profile_url_https:
      d['profile_image_url_https'] = profile_url_https

    return tweets.User.fromJson(d)

  def SetJsonResponse(self, json_str, status_code=200):
    """Set the json response content for twitter_fetcher."""
    self.return_statuscode = [status_code]
    self.return_content = [json_str]

  def SetHtmlResponse(self, html_str, status_code=200):
    """Sets the HTML response content for the URL fetch library."""
    # For now these can be the same function.
    self.SetJsonResponse(html_str, status_code=status_code)

  def SetTimelineResponse(self, twts):
    """Set a timeline response from the given tweets.Tweet objects.

    Args:
      twts: A single tweets.Tweet object or list of tweets.Tweet objects.
    """
    if type(twts) == tweets.Tweet:
      self.SetJsonResponse('[%s]' % twts.toJsonString())
      return

    if type(twts) == list:
      self.SetJsonResponse('[%s]' % ','.join([t.toJsonString() for t in twts]))
      return

    raise WebTestError('Bad argument to SetTimelineResponse: %s', twts)

  def assertTweetDbContents(self, tweet_ids, list_id=''):
    """Assert that all tweets in the DB are in tweet_ids."""
    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(1000)
    self.assertEquals(len(tweet_ids), len(tweet_db))
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, tweet_ids)
      if list_id:
        self.assertEquals(tweet.from_list, list_id)

  def assertTweetDbSize(self, expected_size):
    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(1000)
    self.assertEquals(expected_size, len(tweet_db))

  def assertGameDbSize(self, expected_size):
    query = game_model.Game.query()
    game_db = query.fetch(1000)
    logging.info('Found games: %s', game_db)
    self.assertEquals(expected_size, len(game_db))

  def assertUserDbContents(self, user_ids):
    """Assert that all users in the DB are in user_ids."""
    user_query = tweets.User.query()
    user_db = user_query.fetch(1000)
    self.assertEquals(len(user_ids), len(user_db))
    for user in user_db:
      self.assertIn(user.id_str, user_ids)
