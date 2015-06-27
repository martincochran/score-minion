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

  def testUpdateLists_withFakeData(self):
    """Ensure using fake data from a test file works."""
    self.testapp.get('/tasks/update_lists_rate_limited?fake_data=true')

    list_query = crawl_lists.ManagedLists.query(ancestor=crawl_lists.lists_key())
    list_entries = list_query.fetch(10)
    self.assertEquals(1, len(list_entries))
    self.assertEquals(7, len(list_entries[0].list_ids))
    
  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_allNewTweets(self, mock_add_queue):
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

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  def testCrawlList_retrievalError(self):
    self.SetJsonResponse('')
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('Could not fetch statuses') != -1)

  def testCrawlList_fakeData(self):
    """Verify crawling fake data for the fake list works properly."""

    # List ids to ensure test does not take too long to run.
    list_ids = []
    list_sizes = []

    # Real list ids and sizes. Uncomment this and run if these ever change.
    #list_ids = ['186732484', '186732631', '186814318', '186814882',
        #'186815046', '186926608', '186926651']
    #list_sizes = [62, 71, 64, 67, 83, 87, 90]

    # To add another JSON file that is the string output of a json object
    # printed in the oauth_playground, save the output and then transform it
    # in the following way:
    #
    # quote or delete " chars first
    # \U -> (nothing)
    # \u -> (nothing)
    # None -> null
    # True -> true
    # False -> false
    # u' -> ', but special-case each time u' occurs since a simple substitution
    #   will convert you're into yo"re.
    total_list_size = 0
    list_index = 0
    for list_id in list_ids:
      response = self.testapp.get(
          '/tasks/crawl_list?list_id=%s&fake_data=true' % list_id)
      self.assertEqual(200, response.status_int)
      total_list_size += list_sizes[list_index]
      list_index += 1
      self.assertTweetDbSize(total_list_size)


  def testCrawlList_incrementalNewTweets(self):
    self.SetTimelineResponse(self.CreateTweet(1, ('bob', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['1'], '123')

    # Now update it again - there should be one new entry
    self.SetTimelineResponse([self.CreateTweet(4, ('alice', 3)),
        self.CreateTweet(1, ('bob', 2))])

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['1', '4'], '123')

  def testCrawlList_incrementalNoNewTweets(self):
    self.SetTimelineResponse(self.CreateTweet(1, ('bob', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['1'], '123')

    # Now update it again - there should be one new entry
    self.SetTimelineResponse([self.CreateTweet(1, ('bob', 2))])

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['1'], '123')

  def testCrawlList_noId(self):
    response = self.testapp.get('/tasks/crawl_list')
    self.assertEqual(200, response.status_int)
    self.assertEqual('No list name specified', response.body)

  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_enqueueMore(self, mock_add_queue):
    # Crawl one tweet with a small ID.
    self.SetTimelineResponse(self.CreateTweet(3, ('alice', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['3'], '123')

    # Simulate crawling 2 more without reaching the old tweet.
    twts = [self.CreateTweet(i, ('alice', 2)) for i in range(10, 8, -1)]
    self.SetTimelineResponse(twts)
    response = self.testapp.get('/tasks/crawl_list?list_id=123&num_to_crawl=2')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['3', '10', '9'], '123')

    # Make sure that another call was enqueued to crawl the rest of the
    # timeline.
    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))
    expected_params = {
        'list_id': '123',
        'total_crawled': 2L,
        'max_id': 9L,
        'since_id': 3L,
        'num_to_crawl': 2L,
    }
    self.assertEquals(calls[0], mock.call(
        url='/tasks/crawl_list', method='GET',
        params=expected_params, queue_name='list-statuses'))

  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_simulateCrawlFollowUp(self, mock_add_queue):
    # Crawl one tweet with a small ID.
    self.SetTimelineResponse(self.CreateTweet(3, ('alice', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    # Crawl one tweet with a recent ID which is after the ID that
    # should be indexed.
    self.SetTimelineResponse(self.CreateTweet(10, ('alice', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['10', '3'], '123')

    # This enqueued a crawling request
    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))

    # Simulate crawling 1 more.
    self.SetTimelineResponse([self.CreateTweet(8, ('alice', 2)),
        self.CreateTweet(3, ('alice', 2))])

    params = {
        'list_id': '123',
        'total_crawled': 1L,
        'max_id': 10L,
        'since_id': 3L,
        'num_to_crawl': 200L,
    }
    response = self.testapp.get(
        '/tasks/crawl_list?%s' % '&'.join(
          ['%s=%s' % (i[0], i[1]) for i in params.iteritems()]))
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['10', '8', '3'], '123')

    self.assertEquals(1, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/crawl_list', method='GET',
        params=params, queue_name='list-statuses'))

  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_simulateCrawlFollowUpEnqueueAnother(self, mock_add_queue):
    # Crawl one tweet with a recent ID which is after the ID that
    # should be indexed.
    self.SetTimelineResponse(self.CreateTweet(10, ('alice', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['10'], '123')

    # Simulate crawling 1 more.
    twts = [self.CreateTweet(i, ('alice', 2)) for i in range(7, 5, -1)]
    self.SetTimelineResponse(twts)
    params = {
        'list_id': '123',
        'total_crawled': 2L,
        'max_id': 9L,
        'since_id': 3L,
        'num_to_crawl': 2L,
    }
    response = self.testapp.get(
        '/tasks/crawl_list?%s' % '&'.join(
          ['%s=%s' % (i[0], i[1]) for i in params.iteritems()]))
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['10', '7', '6'], '123')

    # There are still more to crawl since the original tweet has not been
    # returned in the timeline yet.
    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))

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
        params={'list_id': '1234', 'fake_data': ''},
        queue_name='list-statuses'))
    self.assertEquals(calls[1], mock.call(
        url='/tasks/crawl_list', method='GET',
        params={'list_id': '87', 'fake_data': ''}, queue_name='list-statuses'))

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
