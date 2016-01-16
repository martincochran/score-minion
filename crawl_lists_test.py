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

from datetime import date, datetime, timedelta
import json
import logging
import mock
import unittest
import webtest

import test_env_setup
from google.appengine.api import taskqueue

import crawl_lists
from game_model import Game, GameSource, Team
import list_id_bimap
from scores_messages import AgeBracket
from scores_messages import Division
from scores_messages import GameSourceType
from scores_messages import League
import tweets
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
    now = datetime.utcnow()
    fake_tweets = [
        self.CreateTweet(4, ('alice', 3), created_at=now + timedelta(1, 0, 0)),
        self.CreateTweet(1, ('bob', 2), created_at=now)
    ]
    self.SetTimelineResponse(list(fake_tweets))

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['1', '4'], '123')
    self.assertUserDbContents(['2', '3'])
    self.assertGameDbSize(0)

    # Now update it again - there should be no new entries
    self.SetTimelineResponse(list(fake_tweets))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['1', '4'], '123')
    self.assertUserDbContents(['2', '3'])
    self.assertGameDbSize(0)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_updateUserUrl(self, mock_add_queue):
    now = datetime.utcnow()
    fake_tweets = [
        self.CreateTweet(4, ('alice', 3), created_at=now + timedelta(1, 0, 0)),
    ]
    self.SetTimelineResponse(list(fake_tweets))

    # Modify the profile URL
    json_obj = json.loads(self.return_content[0])
    json_obj[0].get('user', {})['profile_image_url_https'] = 'a'
    self.return_content = [json.dumps(json_obj)]

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['4'], '123')
    self.assertUserDbContents(['3'])
    user_query = tweets.User.query().filter(tweets.User.id_64 == 3)
    users = user_query.fetch(1)
    self.assertEquals(1, len(users))
    self.assertEquals('a', users[0].profile_image_url_https)

    # Now update it again - should be a new tweet and the user profile
    # URL should be updated.
    fake_tweets = [
        self.CreateTweet(7, ('alice', 3), created_at=now + timedelta(2, 0, 0)),
    ]
    self.SetTimelineResponse(list(fake_tweets))
    json_obj = json.loads(self.return_content[0])
    json_obj[0].get('user', {})['profile_image_url_https'] = 'b'
    self.return_content = [json.dumps(json_obj)]

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['4', '7'], '123')
    user_query = tweets.User.query().filter(tweets.User.id_64 == 3)
    users = user_query.fetch(1)
    self.assertEquals(1, len(users))
    self.assertEquals('b', users[0].profile_image_url_https)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_updateScreenName(self, mock_add_queue):
    self.CreateUser(3, 'alice').put()
    user_query = tweets.User.query().filter(tweets.User.id_64 == 3)
    users = user_query.fetch(1)
    # Update the case of the screen_name
    users[0].screen_name = 'Alice'
    users[0].put()
    self.assertUserDbContents(['3'])
    now = datetime.utcnow()
    fake_tweets = [
        self.CreateTweet(4, ('alice', 3), created_at=now + timedelta(1, 0, 0)),
    ]
    self.SetTimelineResponse(list(fake_tweets))

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['4'], '123')
    self.assertUserDbContents(['3'])
    user_query = tweets.User.query().filter(tweets.User.id_64 == 3)
    users = user_query.fetch(1)
    self.assertEquals(1, len(users))
    self.assertEquals('alice', users[0].screen_name)

  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_tweetsWithGames(self, mock_add_queue):
    now = datetime.utcnow()
    fake_tweets = [
        self.CreateTweet(4, ('alice', 3), text='5-7', created_at=now),
        self.CreateTweet(1, ('bob', 2), text='3-5', created_at=now)
    ]
    self.SetTimelineResponse(list(fake_tweets))

    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    self.assertTweetDbContents(['1', '4'], '123')
    self.assertUserDbContents(['2', '3'])

    # There should be two games, one for each tweet.
    self.assertGameDbSize(2)

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
    #    '186815046', '186926608', '186926651']
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
        'total_requests_made': 1,
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

    # Crawl two tweets with a recent ID which is after the ID that
    # should be indexed.
    self.SetTimelineResponse([self.CreateTweet(12, ('alice', 2)),
      self.CreateTweet(10, ('alice', 2))])
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['12', '10', '3'], '123')

    # This enqueued a crawling request
    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))

    # Simulate crawling 1 more.
    self.SetTimelineResponse([self.CreateTweet(8, ('alice', 2)),
        self.CreateTweet(3, ('alice', 2))])

    params = {
        'list_id': '123',
        'total_crawled': 2L,
        'max_id': 10L,
        'since_id': 3L,
        'num_to_crawl': 200L,
        'total_requests_made': 1,
    }
    self.assertEquals(calls[0], mock.call(
        url='/tasks/crawl_list', method='GET',
        params=params, queue_name='list-statuses'))

    # Reset the mock and make the request as if it was initiated by the queue.
    mock_add_queue.mock_calls = []
    response = self.testapp.get(
        '/tasks/crawl_list?%s' % '&'.join(
          ['%s=%s' % (i[0], i[1]) for i in params.iteritems()]))
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['12', '10', '8', '3'], '123')

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_stopBackfillOnlyOneCrawled(self, mock_add_queue):
    # Crawl one tweet with a small ID.
    self.SetTimelineResponse(self.CreateTweet(3, ('alice', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    # Crawl two tweets with a recent ID which is after the ID that
    # should be indexed.
    self.SetTimelineResponse([self.CreateTweet(12, ('alice', 2)),
      self.CreateTweet(10, ('alice', 2))])
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['12', '10', '3'], '123')

    # This enqueued a crawling request
    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))

    # Simulate crawling 1 more.
    self.SetTimelineResponse([self.CreateTweet(8, ('alice', 2))])

    params = {
        'list_id': '123',
        'total_crawled': 2L,
        'max_id': 10L,
        'since_id': 3L,
        'num_to_crawl': 200L,
        'total_requests_made': 1,
    }
    self.assertEquals(calls[0], mock.call(
        url='/tasks/crawl_list', method='GET',
        params=params, queue_name='list-statuses'))

    # Reset the mock and make the request as if it was initiated by the queue.
    mock_add_queue.mock_calls = []
    response = self.testapp.get(
        '/tasks/crawl_list?%s' % '&'.join(
          ['%s=%s' % (i[0], i[1]) for i in params.iteritems()]))
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['12', '10', '8', '3'], '123')

    # Even though the original tweet '3' was not returned, we shouldn't have
    # enqueued more because only one tweet was crawled.
    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testCrawlList_stopBackfillMaxRequests(self, mock_add_queue):
    # Crawl one tweet with a small ID.
    self.SetTimelineResponse(self.CreateTweet(3, ('alice', 2)))
    response = self.testapp.get('/tasks/crawl_list?list_id=123')
    self.assertEqual(200, response.status_int)

    # Crawl two tweets with a recent ID which is after the ID that
    # should be indexed.
    self.SetTimelineResponse([self.CreateTweet(12, ('alice', 2)),
      self.CreateTweet(10, ('alice', 2))])
    response = self.testapp.get(
        '/tasks/crawl_list?list_id=123&total_requests_made=%d' % (
          crawl_lists.MAX_REQUESTS - 1))
    self.assertEqual(200, response.status_int)
    self.assertTweetDbContents(['12', '10', '3'], '123')

    # This did not enqueue a crawling request because the maximum number
    # of crawl requests has been made.
    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

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
        'total_requests_made': 1,
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

  def testCrawlAllUsers_noUsers(self):
    """Ensure crawl_all_users handles case when there are no users."""
    response = self.testapp.get('/tasks/crawl_all_lists')
    self.assertEqual(200, response.status_int)
    self.assertEqual('No lists to crawl', response.body)

  @mock.patch.object(taskqueue, 'add')
  def testCrawlAllUsers_someUsers(self, mock_add_queue):
    """Ensure crawl_all_users handles case when there is one user."""
    self.CreateUser(2, 'bob').put()
    response = self.testapp.get('/tasks/crawl_all_users')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('2') != -1)

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/crawl_users', method='POST',
        params={'user_id': '2'},
        queue_name='lookup-users'))

  @mock.patch.object(taskqueue, 'add')
  def testCrawlAllUsers_manyUsers(self, mock_add_queue):
    """Ensure crawl_all_users handles case when there many users."""
    offset = 1000
    num_users = crawl_lists.MAX_USERS_PER_CRAWL_REQUEST + 1
    for i in range(crawl_lists.MAX_USERS_PER_CRAWL_REQUEST + 1):
      self.CreateUser(i + offset, 'bob_%s' % i).put()
    response = self.testapp.get('/tasks/crawl_all_users')
    self.assertEqual(200, response.status_int)

    # Ensure it enqueued requests for all of them.
    logging.info('crawl_users response: %s', response.body)
    self.assertTrue(response.body.find('%s' % num_users) != -1)

    calls = mock_add_queue.mock_calls
    self.assertEquals(2, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/crawl_users', method='POST',
        params={'user_id': ','.join(
          [str(i + offset) for i in range(num_users - 1)])},
        queue_name='lookup-users'))
    self.assertEquals(calls[1], mock.call(
        url='/tasks/crawl_users', method='POST',
        params={'user_id': '%s' % (num_users + offset - 1)},
        queue_name='lookup-users'))
    
  @mock.patch.object(taskqueue, 'add')
  def testCrawlUsers_newScreenName(self, mock_add_queue):
    """Ensure crawl_users updates screen_names if they have changed."""
    # Create the canonical user.
    bob = self.CreateUser(2, 'bob')
    key = bob.key
    json_obj = json.loads(bob.ToJsonString())
    json_obj.get('user', {})['screen_name'] = 'Bob'
    tweets.User.GetOrInsertFromJson(json_obj)

    self.assertUserDbContents(['2'])

    self.SetJsonResponse('[%s]' % bob.ToJsonString())
    response = self.testapp.post('/tasks/crawl_users', params={
      'user_id': '2'})
    self.assertEqual(200, response.status_int)

    self.assertUserDbContents(['2'])

    # Assert that the profile URL was updated in the db.
    users = tweets.User.query().fetch()
    self.assertEquals('bob', users[0].screen_name)

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

  def testFindTeamsInTweet(self):
    """Verify that we can find the teams in a tweet."""
    # Create a user and add it to the db.
    user = self.CreateUser(2, 'bob')
    user.put()

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    twt = self.CreateTweet(1, ('bob', 2))
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {})

    # Make sure we found 'bob' correctly.
    self.assertEquals(2, teams[0].twitter_id)
    self.assertEquals(crawl_lists.UNKNOWN_SR_ID, teams[1].score_reporter_id)

  def testFindTeamsInTweet_newUserThisCrawlCycle(self):
    """Verify a user can be found when it's not in the db but was crawled."""
    # Create a user and add it to the db.
    user = self.CreateUser(2, 'bob')

    user_db = {'2': user}

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    twt = self.CreateTweet(1, ('bob', 2))
    teams = crawl_lists_handler._FindTeamsInTweet(twt, user_db)

    # Make sure we found 'bob' correctly.
    self.assertEquals(2, teams[0].twitter_id)
    self.assertEquals(crawl_lists.UNKNOWN_SR_ID, teams[1].score_reporter_id)

  def testFindTeamsInTweet_userMentionOfSecondTeam(self):
    """Verify a user can be found when it mentions another user."""
    # Create a user and add it to the db.
    bob = self.CreateUser(2, 'bob')
    alice = self.CreateUser(3, 'alice')

    user_db = {'2': bob, '3': alice}

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    twt = self.CreateTweet(1, ('bob', 2))
    twt.entities.user_mentions = [tweets.UserMentionEntity(
      user_id='3', user_id_64=3)]
    teams = crawl_lists_handler._FindTeamsInTweet(twt, user_db)

    # Make sure we found 'bob' correctly.
    self.assertEquals(2, teams[0].twitter_id)
    self.assertEquals(3, teams[1].twitter_id)

  def testFindTeamsInTweet_userMentionOfSecondTeamWrongDivision(self):
    """Verify a user can be found when it mentions another user."""
    # Create a user and add it to the db.
    bob = self.CreateUser(2, 'bob')
    bob.from_list = list_id_bimap.ListIdBiMap.USAU_COLLEGE_OPEN_LIST_ID
    alice = self.CreateUser(3, 'alice')
    alice.from_list = list_id_bimap.ListIdBiMap.USAU_COLLEGE_WOMENS_LIST_ID

    user_db = {'2': bob, '3': alice}

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    twt = self.CreateTweet(1, ('bob', 2))
    twt.entities.user_mentions = [tweets.UserMentionEntity(
      user_id='3', user_id_64=3)]
    teams = crawl_lists_handler._FindTeamsInTweet(twt, user_db)

    # Make sure we found 'bob' correctly.
    self.assertEquals(2, teams[0].twitter_id)
    self.assertEquals(crawl_lists.UNKNOWN_SR_ID, teams[1].score_reporter_id)

  def testFindTeamsInTweet_noExistingUser(self):
    """Handle the case gracefully if the user doesn't exist in db."""
    crawl_lists_handler = crawl_lists.CrawlListHandler()
    twt = self.CreateTweet(1, ('bob', 2))
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {})

    self.assertEquals(None, teams[0].twitter_id)
    self.assertEquals(None, teams[1].twitter_id)

  def testFindMostConsistentGame_noGamesInDb(self):
    """Verify that it doesn't find any consistent games if none exist."""
    crawl_lists_handler = crawl_lists.CrawlListHandler()
    twt = self.CreateTweet(1, ('bob', 2))
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {})
    scores = [0, 0]
    (score, game) = crawl_lists_handler._FindMostConsistentGame(twt, [],
        teams, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU, scores)

    self.assertEquals(0.0, score)
    self.assertEquals(None, game)

  def testFindMostConsistentGame(self):
    """Verify that it finds consistent games if it exists."""
    user = self.CreateUser(2, 'bob')

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob'
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {'2': user})

    source = GameSource(type=GameSourceType.TWITTER,
        home_score=5, away_score=7,
        update_date_time=now - timedelta(minutes=5))
    # Create a game with 'bob' in that division, age_bracket, and league
    game = Game(id_str='new game', teams=teams, scores=[5, 7],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        league=League.USAU, created_at=now, last_modified_at=now,
        sources=[source])
    # Score has to be a plausible update to the game.
    scores = [6, 7]

    (score, found_game) = crawl_lists_handler._FindMostConsistentGame(twt, [game],
        teams, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU, scores)

    # Score should be high since the time of the Tweet is close to the game.
    self.assertTrue(score >= 0.9)
    self.assertEquals(game, found_game)

  def testFindMostConsistentGame_scoreReporter(self):
    """Verify that it finds consistent games if it exists."""
    user = self.CreateUser(2, 'bob')

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob'
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {'2': user})

    # Simulate that this is a game crawled by score reporter weeks ago.
    score_crawl_time = now - timedelta(weeks=5)
    source = GameSource(type=GameSourceType.SCORE_REPORTER,
        home_score=0, away_score=0,
        update_date_time=score_crawl_time)
    # Create a game with 'bob' in that division, age_bracket, and league
    game = Game(id_str='new game', teams=teams, scores=[0, 0],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        start_time=now - timedelta(hours=1),
        league=League.USAU, created_at=score_crawl_time,
        last_modified_at=score_crawl_time, sources=[source])
    # Score has to be a plausible update to the game.
    scores = [2, 3]

    (score, found_game) = crawl_lists_handler._FindMostConsistentGame(twt, [game],
        teams, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU, scores)

    # Score should be high since the time of the Tweet is close to the game.
    self.assertTrue(score >= crawl_lists.GAME_CONSISTENCY_THRESHOLD)
    self.assertEquals(game, found_game)

  def testFindMostConsistentGame_noSourceScores(self):
    """Verify GameSources with no scores are handled."""
    user = self.CreateUser(2, 'bob')

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob'
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {'2': user})

    source = GameSource(type=GameSourceType.TWITTER,
        update_date_time=now - timedelta(minutes=5))
    # Create a game with 'bob' in that division, age_bracket, and league
    game = Game(id_str='new game', teams=teams, scores=[5, 7],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        league=League.USAU, created_at=now, last_modified_at=now,
        sources=[source])

    scores = [6, 7]
    (score, found_game) = crawl_lists_handler._FindMostConsistentGame(twt, [game],
        teams, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU, scores)

    self.assertEqual(0.0, score)
    self.assertEqual(None, found_game)

  def testFindMostConsistentGame_noMatchingGamesWithTeam(self):
    """Verify no consistent game is found if no games with that team exist."""
    user = self.CreateUser(2, 'bob')
    user.put()
    user = self.CreateUser(3, 'alice')
    user.put()

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    now = datetime.utcnow()

    # Create a tweet for a different user than the one in the game.
    twt = self.CreateTweet(1, ('alice', 3), created_at=now)

    # The first team will be 'alice', 2nd will be unknown.
    twt_teams = crawl_lists_handler._FindTeamsInTweet(twt, {})

    twt = self.CreateTweet(2, ('bob', 2), created_at=now)

    # The first team will be 'bob', 2nd will be unknown.
    game_teams = crawl_lists_handler._FindTeamsInTweet(twt, {})

    # Create a game with 'bob' in that division, age_bracket, and league
    game = Game(id_str='new game', teams=game_teams, scores=[5, 7],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        league=League.USAU, created_at=now, last_modified_at=now)

    # When we try to find a game that's consistent with the 'alice' teams
    # it fails because the only known game has 'bob' and an unknown team.
    scores = [0, 0]
    (score, found_game) = crawl_lists_handler._FindMostConsistentGame(twt, [game],
        twt_teams, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU,
        scores)

    self.assertEquals(0.0, score)
    self.assertEquals(None, found_game)

  def testFindMostConsistentGame_matchingGamesWithTeamButNotMatchingTime(self):
    """Verify no consistent game is found if update is too old."""
    user = self.CreateUser(2, 'bob')
    user.put()

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob'
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {})

    # Create a game with 'bob' in that division, age_bracket, and league, but with
    # an old date.
    creation_date = now - timedelta(
        hours=crawl_lists.MAX_LENGTH_OF_GAME_IN_HOURS + 1)
    game = Game(id_str='new game', teams=teams, scores=[5, 7],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        league=League.USAU, created_at=creation_date,
        last_modified_at=creation_date)

    scores = [0, 0]
    (score, found_game) = crawl_lists_handler._FindMostConsistentGame(twt, [game],
        teams, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU, scores)

    self.assertEquals(0.0, score)
    self.assertEquals(None, found_game)

  def testFindMostConsistentGame_matchingTeamButNotMatchingScore(self):
    """Verify no consistent game is found if update is too old."""
    user = self.CreateUser(2, 'bob')
    user.put()

    user = self.CreateUser(3, 'alice')
    user.put()

    user = self.CreateUser(4, 'eve')
    user.put()

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob'
    teams = [Team(twitter_id=2), Team(twitter_id=3)]
    # Create a game that was created by a prior tweet by bob that involved
    # alice's team.
    creation_date = now + timedelta(minutes=30)
    sources = [GameSource(
      home_score=10, away_score=11,
      type=GameSourceType.TWITTER, update_date_time=creation_date)]
    game = Game(id_str='alice / bob game', teams=teams, scores=[10, 11],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        sources=sources, league=League.USAU, created_at=creation_date,
        last_modified_at=creation_date)

    # Now simulate a tweet from alice about a previous game that was
    # crawled in the same timeframe.
    twt = self.CreateTweet(5, ('alice', 3), created_at=now)
    teams = [Team(twitter_id=3), Team(twitter_id=4)]
    creation_date = now
    scores = [13, 5]
    (score, found_game) = crawl_lists_handler._FindMostConsistentGame(twt, [game],
        teams, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU, scores)

    self.assertEquals(0.0, score)
    self.assertEquals(None, found_game)

  def testFindMostConsistentGame_scoreDoesNotMatch(self):
    """Verify that it creates a new games if scores don't match."""
    user = self.CreateUser(2, 'bob')

    crawl_lists_handler = crawl_lists.CrawlListHandler()
    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob'
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {'2': user})

    source = GameSource(type=GameSourceType.TWITTER,
      home_score=15, away_score=12,
        update_date_time=now - timedelta(minutes=5))
    # Create a game with 'bob' in that division, age_bracket, and league
    game = Game(id_str='new game', teams=teams, scores=[15, 12],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        league=League.USAU, created_at=now, last_modified_at=now,
        sources=[source])
    # Score is from a new game, apparently.
    scores = [1, 0]

    (score, found_game) = crawl_lists_handler._FindMostConsistentGame(twt, [game],
        teams, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU, scores)

    self.assertEquals(0.0, score)
    self.assertEquals(None, found_game)

  def testGroupGames(self):
    """Test grouping of games using some real data from Mischief."""
    twts = [
        # Finals vs @PBRawr
        # Almost 80 minutes later, a correction in score.
        ["Er, correction. 13-10 vs @PBRawr.", "22:15:06"],
        # Typo
        ["13-0 for game. Good game @PBRawr!", "20:58:59"],
        ["Matt west. 12-10 game to 13.", "20:56:02"],
        ["40 yards to Sharon for the downwind break. 11-9", "20:47:42"],
        ["Tiring hold. 10-9.", "20:40:08"],
        ["Both o lines hold. Berry to ham makes it 9-7.", "20:24:11"],
        ["Doffense takes half drew to jon, 8-6 over @PBRawr.", "20:09:18"],
        ["Ham to berry, 7-6.", "20:04:22"],
        ["Ellen scores to give the o a break. 6-5 on @PBRawr", "20:00:04"],
        ["Ellen for score. Thanks @SuperflyUlti. 5-4 on @PBRawr", "19:54:10"],
        [".@PBRawr got their break back. 4-4", "19:51:49"],
        ["Things happened. 3-1, up a break on @PBRawr", "19:40:43"],
        # Semis vs alchemy
        ["hucks to Jaffe for game. 15-4, well played everyone", "19:17:18"],
        ["don't worry- mischief hasn't. 14-4 now", "19:09:04"],
        ["Sea turtle catches the s cut. 10-4", "18:57:01"],
        ["still complains about being old. 6-3", "18:31:05"],
        ["Free lesson on boxing out for the kids. 5-3", "18:28:46"],
        ["Sharon makes it easy. 3-2.", "18:21:37"],
        ["3-1. Jenny Wang. That it all.", "18:16:50"],
        ["Game versus alchemy. we hold. 1-0.", "18:11:06"],
        # Quarters vs Platipi
        ["Chuck has it figured out. Berry reels it in. 13-9 game.", "17:57:59"],
        ["enough to overcome our struggle-sesh. 12-9.", "17:53:35"],
        ["the score. 10-6. Actually 11-6 now.", "17:37:52"],
        ["herthe double happiness. 8-4, half.", "17:08:02"],
        ["7-4. Not the prettiest but not the worst.", "17:04:42"],
        ["5-3 now. They broke us then Sean Ham broke", "16:57:08"],
        ["Jaffe lefty to craw. 4-1 old guys.", "16:50:14"],
        ["Combined age: 63. Score: 3-1.", "16:48:54"],
        ["Mischief v platipi. Three quick points. 2-1 red team", "16:47:00"],
    ]

    handler = crawl_lists.CrawlListHandler()

    # Create tweets from above data, then see how they are grouped.
    date_fmt = 'Sun Jun 07 %s 2015'
    id = 100
    twt_objs = []
    games = []
    user_map = {
        '2': self.CreateUser(2, 'mischief'),
    }
    d = Division.MIXED
    a = AgeBracket.NO_RESTRICTION
    l = League.USAU
    for twt in twts:
      t = datetime.strptime(date_fmt % twt[1], tweets.DATE_PARSE_FMT_STR)
      twt = self.CreateTweet(id, ('mischief', 2), text=twt[0], created_at=t)
      id -= 1
      handler._PossiblyAddTweetToGame(twt, [], games, user_map, d, a, l)

    logging.info(games)
    self.assertEqual(3, len(games))
    self.assertEqual(12, len(games[0].sources))
    self.assertEqual(8, len(games[1].sources))
    self.assertEqual(9, len(games[2].sources))

  def testFindScoreIndicies(self):
    """Sanity test for basic cases in FindScoreIndices."""
    crawl_lists_handler = crawl_lists.CrawlListHandler()
    integers = [
        tweets.IntegerEntity(num=5, start_idx=0, end_idx=1),
        tweets.IntegerEntity(num=7, start_idx=3, end_idx=4)
    ]
    self.assertEquals([0, 1], crawl_lists_handler._FindScoreIndicies(
      integers, '5-7'))

    # Not the first score entity.
    integers = [
        tweets.IntegerEntity(num=5, start_idx=0, end_idx=1),
        tweets.IntegerEntity(num=7, start_idx=10, end_idx=11),
        tweets.IntegerEntity(num=9, start_idx=13, end_idx=14)
    ]
    self.assertEquals([1, 2], crawl_lists_handler._FindScoreIndicies(
      integers, '5         7-9'))

    # Integers too far apart.
    integers = [
        tweets.IntegerEntity(num=5, start_idx=0, end_idx=1),
        tweets.IntegerEntity(num=7, start_idx=13, end_idx=14)
    ]
    self.assertEquals([], crawl_lists_handler._FindScoreIndicies(
      integers, '5               7'))

    # No '-' found
    integers = [
        tweets.IntegerEntity(num=5, start_idx=0, end_idx=1),
        tweets.IntegerEntity(num=7, start_idx=10, end_idx=11),
        tweets.IntegerEntity(num=9, start_idx=13, end_idx=14)
    ]
    self.assertEquals([], crawl_lists_handler._FindScoreIndicies(
      integers, '5         7/9'))

  def testPossiblyAddTweetToGame_dontAddTweetCases(self):
    """Sanity test for cases where a game should not be created from a tweet."""
    crawl_lists_handler = crawl_lists.CrawlListHandler()

    added_games = []
    # Gracefully handle twt being None.
    crawl_lists_handler._PossiblyAddTweetToGame(None, [], added_games, {}, None,
        None, None)
    self.assertEquals([], added_games)

    # Make a tweet with no integer entities.
    twt = self.CreateTweet(1, ('bob', 2))
    self.assertFalse(twt.two_or_more_integers)
    crawl_lists_handler._PossiblyAddTweetToGame(twt, [], added_games, {},
        Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], added_games)

    # Now there are integer entities but they're too big.
    twt = self.CreateTweet(1, ('bob', 2), text='50-55')
    self.assertTrue(twt.two_or_more_integers)
    crawl_lists_handler._PossiblyAddTweetToGame(twt, [], added_games, {},
        Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], added_games)

    # There are two numbers but it looks like a date, not a score.
    twt = self.CreateTweet(1, ('bob', 2), text='5/5')
    self.assertTrue(twt.two_or_more_integers)
    crawl_lists_handler._PossiblyAddTweetToGame(twt, [], added_games, {},
        Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], added_games)

  def testPossiblyAddTweetToGame_newGame(self):
    """Sanity test for cases where a game should be created from a tweet."""
    crawl_lists_handler = crawl_lists.CrawlListHandler()

    # Create a tweet with valid integer entities.
    twt = self.CreateTweet(1, ('bob', 2), text='5-7')
    self.assertTrue(twt.two_or_more_integers)

    added_games = []
    crawl_lists_handler._PossiblyAddTweetToGame(twt, [], added_games, {},
        Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals(1, len(added_games))

  def testPossiblyAddTweetToGame_existingGame(self):
    """Sanity test for cases where a game be updated from a tweet."""
    crawl_lists_handler = crawl_lists.CrawlListHandler()

    user = self.CreateUser(2, 'bob')
    user.put()

    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob'
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {})

    # Create a game with 'bob' in that division, age_bracket, and league
    source = GameSource(type=GameSourceType.TWITTER,
        home_score=3, away_score=5, update_date_time=now)
    game = Game(id_str='new game', teams=teams, scores=[3, 5],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        league=League.USAU, created_at=now, last_modified_at=now,
        sources=[source])
    sources_length = len(game.sources)

    # Create a tweet with valid integer entities.
    twt = self.CreateTweet(1, ('bob', 2), text='5-7')
    self.assertTrue(twt.two_or_more_integers)

    # Test case where the source was in an existing game.
    existing_games = [game]
    added_games = []
    crawl_lists_handler._PossiblyAddTweetToGame(twt, existing_games,
        added_games, {}, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], added_games)
    self.assertEquals(sources_length + 1, len(game.sources))

    # Add another twt
    twt = self.CreateTweet(2, ('bob', 2), text='7-9')
    self.assertTrue(twt.two_or_more_integers)

    # Test case where the source was in an added game.
    sources_length = len(game.sources)
    existing_games = []
    added_games = [game]
    crawl_lists_handler._PossiblyAddTweetToGame(twt, existing_games,
        added_games, {}, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], existing_games)
    self.assertEquals(1, len(added_games))
    self.assertEquals(sources_length + 1, len(game.sources))

  def testPossiblyAddTweetToGame_existingGameNewMention(self):
    """Test where a game and its teams should be updated from a tweet."""
    user_map = {
        '2': self.CreateUser(2, 'bob'),
        '3': self.CreateUser(3, 'alice'),
        '4': self.CreateUser(3, 'eve'),
    }

    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob' and the second will be 'unknown'.
    crawl_lists_handler = crawl_lists.CrawlListHandler()
    teams = crawl_lists_handler._FindTeamsInTweet(twt, user_map)

    # Create a game with 'bob' in that division, age_bracket, and league
    source = GameSource(type=GameSourceType.TWITTER,
        home_score=3, away_score=5, update_date_time=now)
    game = Game(id_str='new game', teams=teams, scores=[3, 5],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        league=League.USAU, created_at=now, last_modified_at=now,
        sources=[source])
    sources_length = len(game.sources)

    # Create a tweet with valid integer entities and a user mention.
    twt = self.CreateTweet(1, ('bob', 2), text='5-7')
    twt.entities.user_mentions = [tweets.UserMentionEntity(
      user_id='3', user_id_64=3)]
    self.assertTrue(twt.two_or_more_integers)

    # Test case where the source was in an existing game.
    existing_games = [game]
    added_games = []
    crawl_lists_handler._PossiblyAddTweetToGame(twt, existing_games,
        added_games, user_map, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], added_games)
    self.assertEquals(sources_length + 1, len(game.sources))

    # Verify the second team is updated from that tweet.
    self.assertEquals(2, game.teams[0].twitter_id)
    self.assertEquals(3, game.teams[1].twitter_id)

    # Add another twt but with a different user mention.
    twt = self.CreateTweet(2, ('bob', 2), text='7-9')
    twt.entities.user_mentions = [tweets.UserMentionEntity(
      user_id='4', user_id_64=4)]
    self.assertTrue(twt.two_or_more_integers)

    # Tweet is added to the game, but the new team is *not* added (see
    # comment in crawl_lists.CrawListsHandler._MergeTeamsIntoGame for why).
    crawl_lists_handler._PossiblyAddTweetToGame(twt, existing_games,
        added_games, user_map, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], added_games)
    self.assertEquals(sources_length + 2, len(game.sources))

    # Verify the second team is updated from that tweet.
    self.assertEquals(2, game.teams[0].twitter_id)
    self.assertEquals(3, game.teams[1].twitter_id)

  def testPossiblyAddTweetToGame_eachTweetOnlyOnce(self):
    """Don't add the same tweet source twice."""
    crawl_lists_handler = crawl_lists.CrawlListHandler()

    user = self.CreateUser(2, 'bob')
    user.put()

    now = datetime.utcnow()
    twt = self.CreateTweet(1, ('bob', 2), created_at=now)

    # The first team will be 'bob'
    teams = crawl_lists_handler._FindTeamsInTweet(twt, {})

    # Create a game with 'bob' in that division, age_bracket, and league
    source = GameSource(type=GameSourceType.TWITTER,
        home_score=3, away_score=5, update_date_time=now)
    game = Game(id_str='new game', teams=teams, scores=[3, 5],
        division=Division.OPEN, age_bracket=AgeBracket.NO_RESTRICTION,
        league=League.USAU, created_at=now, last_modified_at=now,
        sources=[source])
    sources_length = len(game.sources)

    # Create a tweet with valid integer entities.
    twt = self.CreateTweet(1, ('bob', 2))
    twt.text = '5-7'
    twt.entities.integers = [
        tweets.IntegerEntity(num=5, start_idx=0, end_idx=1),
        tweets.IntegerEntity(num=7, start_idx=3, end_idx=4)
    ]
    self.assertTrue(twt.two_or_more_integers)

    # Test case where the source was in an existing game.
    existing_games = [game]
    added_games = []
    crawl_lists_handler._PossiblyAddTweetToGame(twt, existing_games,
        added_games, {}, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], added_games)
    self.assertEquals(sources_length + 1, len(game.sources))

    # Try to add the same tweet to the game again.
    crawl_lists_handler._PossiblyAddTweetToGame(twt, existing_games,
        added_games, {}, Division.OPEN, AgeBracket.NO_RESTRICTION, League.USAU)
    self.assertEquals([], added_games)

    # The sources length should be unchanged
    self.assertEquals(sources_length + 1, len(game.sources))

  def testBackfill_parseDuration(self):
    """Ensure parsing of the data parameter is done correctly."""
    backfill_handler = crawl_lists.BackfillGamesHandler()

    # Bad input formats.
    self.assertIsNone(backfill_handler._ParseDuration('5'))
    self.assertIsNone(backfill_handler._ParseDuration('w'))
    self.assertIsNone(backfill_handler._ParseDuration('m'))
    self.assertIsNone(backfill_handler._ParseDuration('5s'))
    self.assertIsNone(backfill_handler._ParseDuration('5d'))
    self.assertIsNone(backfill_handler._ParseDuration('5y'))
    self.assertIsNone(backfill_handler._ParseDuration('ww'))

    # Too long of a duration.
    self.assertIsNone(backfill_handler._ParseDuration('7m'))
    self.assertIsNone(backfill_handler._ParseDuration('50w'))

    # Non-positive durations.
    self.assertIsNone(backfill_handler._ParseDuration('-2w'))
    self.assertIsNone(backfill_handler._ParseDuration('0w'))

    self.assertEqual(timedelta(weeks=5), backfill_handler._ParseDuration('5w'))
    self.assertEqual(timedelta(weeks=12), backfill_handler._ParseDuration('3m'))

  def testParseDate(self):
    """Ensure parsing of the date parameter is done correctly."""
    # Bad input format.
    self.assertIsNone(crawl_lists.ParseDate('not valid'))

    parsed_date = crawl_lists.ParseDate('01/10/2015')
    self.assertEqual(2015, parsed_date.year)
    self.assertEqual(1, parsed_date.month)
    self.assertEqual(10, parsed_date.day)

  def testGenerateBackfillDates(self):
    """Verify generation of backfill dates works as expected."""
    backfill_handler = crawl_lists.BackfillGamesHandler()

    duration = timedelta(weeks=5)

    # Doomsday for 2015 is Saturday
    start_date = datetime(2015, 2, 28)

    days = backfill_handler._GenerateBackfillDates(duration, start_date)
    self.assertEqual(5, len(days))

    # The first date should be the closest Wednesday
    first_date = start_date - timedelta(days=3)
    self.assertEqual(first_date, days[0])

    for i in range(1, 5):
      self.assertEqual(first_date - timedelta(weeks=i), days[i])

  @mock.patch.object(taskqueue, 'add')
  def testBackfillGames_badInputs(self, mock_add_queue):
    """Test handling of various error conditions on backfill games."""
    # Add a couple lists to the database.
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}, {"id_str": "87"}]}')
    self.testapp.get('/tasks/update_lists_rate_limited')

    response = self.testapp.get('/tasks/backfill_games')
    self.assertEqual(200, response.status_int)

    response = self.testapp.get('/tasks/backfill_games?duration=ww')
    self.assertEqual(200, response.status_int)

    response = self.testapp.get('/tasks/backfill_games?start_date=02/28/2015')
    self.assertEqual(200, response.status_int)

    response = self.testapp.get(
        '/tasks/backfill_games?duration=1m&start_date=hey')
    self.assertEqual(200, response.status_int)

    self.assertEquals(0, len(mock_add_queue.mock_calls))

  @mock.patch.object(taskqueue, 'add')
  def testBackfillGames_validInputs(self, mock_add_queue):
    """Test backfill when correct inputs are specified."""
    # Add a couple lists to the database.
    self.SetJsonResponse('{"lists": [{"id_str": "1234"}, {"id_str": "87"}]}')
    self.testapp.get('/tasks/update_lists_rate_limited')

    response = self.testapp.get('/tasks/backfill_games?duration=1w')
    self.assertEqual(200, response.status_int)
    self.assertEquals(2, len(mock_add_queue.mock_calls))

    # TODO: assert the call has the date formatted correctly.

    mock_add_queue.mock_calls = []
    response = self.testapp.get(
        '/tasks/backfill_games?duration=5w&start_date=02/28/2015')
    self.assertEqual(200, response.status_int)
    self.assertEquals(10, len(mock_add_queue.mock_calls))

  def testBackfillGames(self):
    """Sanity test for backfilling Games from the Tweet db."""
    crawl_lists_handler = crawl_lists.CrawlListHandler()

    # Add a tweet to the db
    creation_date = datetime(2015, 2, 28)
    self.CreateTweet(1, ('bob', 2), text='5-7', created_at=creation_date,
        list_id='123').put()
    self.CreateUser(2, 'bob').put()

    creation_date_str = (creation_date - timedelta(days=3)).strftime('%m/%d/%Y')
    response = self.testapp.get(
        '/tasks/crawl_list?list_id=123&backfill_date=%s' % creation_date_str)
    self.assertEqual(200, response.status_int)
    self.assertGameDbSize(1)
    
    # Backfill again - should still only be one game.
    response = self.testapp.get(
        '/tasks/crawl_list?list_id=123&backfill_date=%s' % creation_date_str)
    self.assertEqual(200, response.status_int)
    self.assertGameDbSize(1)

  def testUpdateGameConsistency(self):
    """Test updating games with only one tweet."""
    # Create game with only one team and one game source.
    game = Game()
    self.CreateUser(2, 'bob').put()
    twt = self.CreateTweet(5, ('bob', 2), 'up 5-7')
    game.sources = [GameSource.FromTweet(twt, [5, 7])]

    game.teams = [Team(score_reporter_id=crawl_lists.UNKNOWN_SR_ID)]
    crawl_lists_handler = crawl_lists.CrawlListHandler()
    crawl_lists_handler._UpdateGameConsistency(game, {})
    self.assertEqual(2, len(game.teams))
    self.assertEqual(2, game.teams[0].twitter_id)

    # Update it again - no changes should have been made.
    crawl_lists_handler._UpdateGameConsistency(game, {})
    self.assertEqual(2, len(game.teams))
    self.assertEqual(2, game.teams[0].twitter_id)


if __name__ == '__main__':
  unittest.main()
