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

from datetime import datetime, timedelta
import json
import logging
import mock
import os
import unittest
import webtest

import test_env_setup

from google.appengine.api import app_identity
from google.appengine.api import taskqueue
from google.appengine.ext import testbed

import endpoints
from endpoints import api_config

import tweets

# Mock out the endpoints method
def null_decorator(*args, **kwargs):
    def decorator(method):
        def wrapper(*args, **kwargs):
            return method(*args, **kwargs)
        return wrapper
    return decorator

endpoints.method = null_decorator

# For some reason this is necessary before importing scores_api
# and using endpoints.
os.environ['CURRENT_VERSION_ID'] = '1.2'
import scores_api
import scores_messages
import web_test_base

class ScoresApiTest(web_test_base.WebTestBase):
  def setUp(self):
    super(ScoresApiTest, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_taskqueue_stub()
    self.testbed.init_datastore_v3_stub()
    self.api = scores_api.ScoresApi()

    self.testapp = webtest.TestApp(scores_api.app)

  def testSanityGetGames(self):
    """Ensure no exceptions are thrown on simple requests to GetGames."""
    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

  def testSanityGetGameInfo(self):
    """Ensure no exceptions are thrown on simple requests to GetGameInfo."""
    self.assertEqual(scores_messages.GameInfoResponse(),
        self.api.GetGameInfo(scores_messages.GameInfoRequest()))

  @mock.patch.object(app_identity, 'app_identity')
  def testGetGames_gameTweet(self, mock_app_identity):
    """Verify the API handles the case where a game is returned."""
    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    twt = tweets.Tweet.fromJson(
        json.loads(
          '{"user": {"id_str": "1234", "id": 1234, "screen_name": "bob"},'
          '"id":232,'
          '"id_str":"232",'
          '"text":"Up 12-11.",'
          '"lang":"en"}'))

    # Pretend we crawled this from an club open list.
    twt.from_list = '186732484'

    twt.put()
    request = scores_messages.GamesRequest()
    request.league = scores_messages.League.USAU
    request.division = scores_messages.Division.OPEN
    request.age_bracket = scores_messages.AgeBracket.NO_RESTRICTION

    response = self.api.GetGames(request)
    self.assertEquals(1, len(response.games))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_noTriggerCrawl(self, mock_add_queue, mock_app_identity):
    """Ensure crawl is not triggered if the datebase is up-to-date."""
    # Add a tweet to the database that was recently crawled.
    twt = self.CreateTweet('2', ['bob', '5'])
    twt.put()

    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_triggerCrawl(self, mock_add_queue, mock_app_identity):
    """Ensure crawl is triggered if the database is stale."""
    # Add a tweet to the database that was crawled yesterday.
    yesterday_date = datetime.now() - timedelta(days=1)

    # Subtract the delta that's used in the API logic.
    yesterday_date = yesterday_date - timedelta(
        hours=scores_api.MAX_HOURS_CRAWL_LATENCY)
    twt = self.CreateTweet('2', ['bob', '5'], created_at=yesterday_date)
    twt.put()

    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_noTweetstriggerCrawl(self, mock_add_queue, mock_app_identity):
    """Ensure crawl is triggered when there are no tweets."""
    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))


if __name__ == '__main__':
  unittest.main()
