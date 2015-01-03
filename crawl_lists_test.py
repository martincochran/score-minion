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
import mock
import unittest
import webtest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()
from google.appengine.api import taskqueue

import crawl_lists
import web_test_base


class CrawlListsTest(web_test_base.WebTestBase):
  def setUp(self):
    super(CrawlListsTest, self).setUp()
    self.testapp = webtest.TestApp(crawl_lists.app)

  def testUpdateLists(self):
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}]}')

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    self.assertFalse(list_query.fetch(10))

    response = self.testapp.get('/tasks/update_lists_rate_limited')
    self.assertEqual(200, response.status_int)

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))
    self.assertEquals('1234', list_entries[0].list_ids[0])

  def testUpdateLists_retrievalError(self):
    self.return_statuscode = [200]
    self.return_content = ['']

    response = self.testapp.get('/tasks/update_lists_rate_limited')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('Could not retrieve lists') != -1)

  def testUpdateLists_withSavedListNoUpdate(self):
    # Return one list from the API, and store it.
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}]}')
    self.testapp.get('/tasks/update_lists_rate_limited')

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))

    # Now call it again - the saved lists should not change
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}]}')

    response = self.testapp.get('/tasks/update_lists_rate_limited')
    self.assertEqual(200, response.status_int)

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))

  def testUpdateLists_withSavedListAndUpdate(self):
    # Return one list from the API, and store it.
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}]}')
    self.testapp.get('/tasks/update_lists_rate_limited')

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))

    # Now call it again - the new list should be added.
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}, {"id_str": "87"}]}')
    response = self.testapp.get('/tasks/update_lists_rate_limited')
    self.assertEqual(200, response.status_int)

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(2, len(list_entries[0].list_ids))

  def testUpdateLists_withSavedListAndUpdateWithNoElements(self):
    # Return one list from the API, and store it.
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}]}')
    self.testapp.get('/tasks/update_lists_rate_limited')

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(1, len(list_entries[0].list_ids))

    # Now call it again - there should be no list
    self.SetJsonResponse('{"lists": []}')
    response = self.testapp.get('/tasks/update_lists_rate_limited')
    self.assertEqual(200, response.status_int)

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(0, len(list_entries[0].list_ids))
 
  def testCrawlList_allNewTweets(self):
    now = datetime.datetime.now()
    fake_tweets = [
        self.CreateTweet(4, ('alice', 3), created_at=now + datetime.timedelta(1, 0, 0)),
        self.CreateTweet(1, ('bob', 2), created_at=now)
    ]
    self.SetTimelineResponse(list(fake_tweets))

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['1', '4'], '123')
    self.assertUserDbContents(['2', '3'])

    # Now update it again - there should be no new entries
    self.SetTimelineResponse(list(fake_tweets))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['1', '4'], '123')
    self.assertUserDbContents(['2', '3'])

  def testCrawlList_retrievalError(self):
    self.SetJsonResponse('')
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('Could not fetch statuses') != -1)

  def testCrawlList_incrementalNewTweets(self):
    self.SetTimelineResponse(self.CreateTweet(1, ('bob', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['1'], '123')

    # Now update it again - there should be one new entry
    self.SetTimelineResponse(self.CreateTweet(4, ('alice', 3)))

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['1', '4'], '123')

  def testCrawlList_noId(self):
    response = self.testapp.get('/tasks/crawl_list')
    self.assertEqual(200, response.status_int)
    self.assertEqual('No list name specified', response.body)

  def testCrawlAllLists_noLists(self):
    response = self.testapp.get('/tasks/crawl_all_lists')
    self.assertEqual(200, response.status_int)
    self.assertEqual('No lists to crawl', response.body)

  @mock.patch.object(taskqueue, 'add')
  def testCrawlAllLists_someLists(self, mock_add_queue):
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}, {"id_str": "87"}]}')
    self.testapp.get('/tasks/update_lists_rate_limited')

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

  @mock.patch.object(taskqueue, 'add')
  def testUpdateLists_cronEntryPoint(self, mock_add_queue):
    response = self.testapp.get('/tasks/update_lists')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('Enqueued') != -1)

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/update_lists_rate_limited', method='GET',
        queue_name='list-lists'))


if __name__ == '__main__':
  unittest.main()
