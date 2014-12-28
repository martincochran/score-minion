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

import unittest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()

import webapp2
import webtest

from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_stub
from google.appengine.ext import testbed
from google.appengine.ext.ndb import stats

import accounts
import tweets

class AccountsTest(unittest.TestCase):
  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_urlfetch_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_user_stub()
    self.url_fetch_stub = self.testbed.get_stub(testbed.URLFETCH_SERVICE_NAME)

    self.return_statuscode = [200]
    self.return_content = ['[{"user": {"id_str": "1234", "screen_name": "bob"}}]']

    # Stub out the call to fetch the URL
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      response.set_statuscode(self.return_statuscode.pop(0))
      response.set_content(self.return_content.pop(0))

    self.saved_retrieve_url = self.url_fetch_stub._RetrieveURL
    self.url_fetch_stub._RetrieveURL = _FakeFetch

    self.testapp = webtest.TestApp(accounts.app)

  def tearDown(self):
    # Reset the URL stub to the original function
    self.url_fetch_stub._RetrieveURL = self.saved_retrieve_url
    self.testbed.deactivate()

  def testSanityGet(self):
    self.assertEqual(200, self.testapp.get('/accounts').status_int)

  def testFollowAccount(self):
    response = self.testapp.post('/accounts/follow_account', {'account': 'bob'})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') != -1)

  def testDeleteAccount(self):
    params = {'account': 'bob'}
    # First add an account
    self.testapp.post('/accounts/follow_account', params)

    # Now delete it
    response = self.testapp.post('/accounts/delete_account', params)

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') == -1)

  def testDeleteAllAccounts(self):
    self.return_statuscode = [200, 200]
    self.return_content = [
        '[{"user": {"id_str": "1234", "screen_name": "bob"}}]',
        '[{"user": {"id_str": "9999", "screen_name": "steve"}}]',
    ]

    self.testapp.post('/accounts/follow_account', {'account': 'bob'})
    self.testapp.post('/accounts/follow_account', {'account': 'steve'})
    response = self.testapp.post('/accounts/delete_all_accounts', {})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') == -1)
    self.assertTrue(response.body.find('steve') == -1)

  def testDeleteAllAccounts(self):
    self.return_statuscode = [200, 200]
    self.return_content = [
        '[{"user": {"id_str": "1234", "screen_name": "bob"}}]',
        '[{"user": {"id_str": "9999", "screen_name": "steve"}}]',
    ]

    self.testapp.post('/accounts/follow_account', {'account': 'bob'})
    self.testapp.post('/accounts/follow_account', {'account': 'steve'})
    response = self.testapp.post('/accounts/delete_all_accounts', {})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') == -1)
    self.assertTrue(response.body.find('steve') == -1)

  def testDeleteAllTweets(self):
    self.return_content = [
        '[{"user": {"id_str": "1234", "screen_name": "bob"}, "id_str": "123"}]',
    ]

    # First add an account
    self.testapp.post('/accounts/follow_account', {'account': 'bob'})

    # Ensure there is at least one tweet in the db
    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(1000)
    self.assertEquals(1, len(tweet_db))

    # Now delete it
    response = self.testapp.post('/accounts/delete_all_tweets', {})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(1000)
    self.assertFalse(tweet_db)

    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # The account is still there, though
    self.assertTrue(response.body.find('bob') != -1)

  def testRecrawl(self):
    self.return_statuscode = [200, 200, 200, 200]
    self.return_content = [
        '[{"user": {"id_str": "1234", "screen_name": "bob"}, "id_str": "123"}]',
        '[{"user": {"id_str": "999", "screen_name": "steve"}, "id_str": "456"}]',
        '[{"user": {"id_str": "1234", "screen_name": "bob"}, "id_str": "777"}]',
        '[{"user": {"id_str": "999", "screen_name": "steve"}, "id_str": "888"}]',
    ]

    # First add an account
    self.testapp.post('/accounts/follow_account', {'account': 'bob'})
    self.testapp.post('/accounts/follow_account', {'account': 'steve'})

    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(1000)
    self.assertEquals(2, len(tweet_db))
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, ['123', '456'])

    # Now delete it
    response = self.testapp.post('/accounts/recrawl', {})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)

    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(1000)
    self.assertEquals(2, len(tweet_db))

    # The tweets are different
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, ['777', '888'])

    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # The account is still there, though
    self.assertTrue(response.body.find('bob') != -1)
    self.assertTrue(response.body.find('steve') != -1)


if __name__ == '__main__':
  unittest.main()
