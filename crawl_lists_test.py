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

import mock
from mock import patch

import unittest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()

import webapp2
import webtest

from google.appengine.api import taskqueue
from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_service_pb
from google.appengine.api import urlfetch_stub
from google.appengine.ext import testbed
from google.appengine.runtime import apiproxy_errors

import crawl_lists
import oauth_token_manager
import tweets
import twitter_fetcher


class CrawlListsTest(unittest.TestCase):
  def setUp(self):
    # TODO: refactor test env setup into a base test class
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_taskqueue_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_urlfetch_stub()
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

    self.taskqueue_stub = self.testbed.get_stub(testbed.TASKQUEUE_SERVICE_NAME)

    self.testapp = webtest.TestApp(crawl_lists.app)


  def tearDown(self):
    # Reset the URL stub to the original function
    self.testbed.deactivate()

  def testUpdateLists(self):
    self.return_statuscode = [200]
    self.return_content = ['{"lists": [{"id_str": "1234"}]}']

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    self.assertFalse(list_query.fetch(10))

    response = self.testapp.get('/tasks/update_lists')
    self.assertEqual(200, response.status_int)

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))
    self.assertEquals('1234', list_entries[0].list_ids[0])

  def testUpdateLists_withSavedListNoUpdate(self):
    # Return one list from the API, and store it.
    self.return_statuscode = [200]
    self.return_content = ['{"lists": [{"id_str": "1234"}]}']
    self.testapp.get('/tasks/update_lists')

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))

    # Now call it again - the saved lists should not change
    self.return_statuscode = [200]
    self.return_content = ['{"lists": [{"id_str": "1234"}]}']

    response = self.testapp.get('/tasks/update_lists')
    self.assertEqual(200, response.status_int)

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))

  def testUpdateLists_withSavedListAndUpdate(self):
    # Return one list from the API, and store it.
    self.return_statuscode = [200]
    self.return_content = ['{"lists": [{"id_str": "1234"}]}']
    self.testapp.get('/tasks/update_lists')

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))

    # Now call it again - the saved lists should not change
    self.return_statuscode = [200]
    self.return_content = ['{"lists": [{"id_str": "1234"}, {"id_str": "87"}]}']

    response = self.testapp.get('/tasks/update_lists')
    self.assertEqual(200, response.status_int)

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(2, len(list_entries[0].list_ids))

  def testUpdateLists_withSavedListAndUpdateWithNoElements(self):
    # Return one list from the API, and store it.
    self.return_statuscode = [200]
    self.return_content = ['{"lists": [{"id_str": "1234"}]}']
    self.testapp.get('/tasks/update_lists')

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))

    # Now call it again - the saved lists should not change
    self.return_statuscode = [200]
    self.return_content = ['{"lists": []}']

    response = self.testapp.get('/tasks/update_lists')
    self.assertEqual(200, response.status_int)

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(0, len(list_entries[0].list_ids))
 
  def testCrawlList_allNewTweets(self):
    fake_content = ['[%s]' % ','.join([
        '{"user": {"id_str": "3"}, "id_str": "4", "created_at": "Wed Dec 12 21:00:24 +0000 2014"}',
        '{"user": {"id_str": "2"}, "id_str": "1", "created_at": "Wed Dec 11 21:00:24 +0000 2014"}',
    ])]
    self.return_statuscode = [200]
    self.return_content = list(fake_content)

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(10)
    self.assertEquals(2, len(tweet_db))
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, ['1', '4'])
      self.assertEquals(tweet.from_list, '123')

    # Now update it again - there should be no new entries
    self.return_statuscode = [200]
    self.return_content = list(fake_content)

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(10)
    self.assertEquals(2, len(tweet_db))
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, ['1', '4'])
      self.assertEquals(tweet.from_list, '123')

  def testCrawlList_incrementalNewTweets(self):
    self.return_statuscode = [200]
    self.return_content = ['[%s]' % ','.join([
        '{"user": {"id_str": "2", "screen_name": "bob"}, "id_str": "1"}',
    ])]
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(10)
    self.assertEquals(1, len(tweet_db))
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, ['1'])
      self.assertEquals(tweet.from_list, '123')

    # Now update it again - there should be one new entries
    self.return_statuscode = [200]
    self.return_content = ['[%s]' % ','.join([
        '{"user": {"id_str": "3", "screen_name": "alice"}, "id_str": "4"}'
    ])]

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(10)
    self.assertEquals(2, len(tweet_db))
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, ['1', '4'])

  def testCrawlList_incrementalOldTweets(self):
    self.return_statuscode = [200]
    self.return_content = ['[%s]' % ','.join([
        '{"user": {"id_str": "3"}, "id_str": "4", "created_at": "Wed Dec 10 21:00:24 +0000 2014"}'
    ])]
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(10)
    self.assertEquals(1, len(tweet_db))
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, ['4'])

    # Now update it again - there should be one new entries.  The 2nd entry is
    # too old and has too low a status ID to be indexed.  The indexer stops
    # looking at the timeline at that point.
    self.return_statuscode = [200]
    self.return_content = ['[%s]' % ','.join([
        '{"user": {"id_str": "5"}, "id_str": "6", "created_at": "Wed Dec 11 21:00:24 +0000 2014"}',
        '{"user": {"id_str": "2"}, "id_str": "1", "created_at": "Wed Dec 09 21:00:24 +0000 2014"}',
        '{"user": {"id_str": "7"}, "id_str": "8", "created_at": "Wed Dec 12 21:00:24 +0000 2014"}'
    ])]

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    tweet_query = tweets.Tweet.query()
    tweet_db = tweet_query.fetch(10)
    self.assertEquals(2, len(tweet_db))
    for tweet in tweet_db:
      self.assertIn(tweet.id_str, ['6', '4'])
 
  def testCrawlList_noId(self):
    response = self.testapp.get('/tasks/crawl_list')
    self.assertEqual(200, response.status_int)
    self.assertEqual('No list name specified', response.body)

  def testCrawlAllLists_noLists(self):
    response = self.testapp.get('/tasks/crawl_all_lists')
    self.assertEqual(200, response.status_int)
    self.assertEqual('No lists to crawl', response.body)

  @patch.object(taskqueue, 'add')
  def testCrawlAllLists_someLists(self, mock_add_queue):
    self.return_statuscode = [200]
    self.return_content = ['{"lists": [{"id_str": "1234"}, {"id_str": "87"}]}']
    self.testapp.get('/tasks/update_lists')

    response = self.testapp.get('/tasks/crawl_all_lists')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('1234') != -1)

    calls = mock_add_queue.mock_calls
    self.assertEquals(2, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/crawl_list', method='GET',
        params={'list_id': '1234'}, queue_name='list-statuses'))
    self.assertEquals(calls[1], mock.call(
        url='/tasks/crawl_list', method='GET',
        params={'list_id': '87'}, queue_name='list-statuses'))

  def testUpdateLatestStatus(self):
    pass


if __name__ == '__main__':
  unittest.main()
