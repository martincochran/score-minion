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
import logging
import os

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

import webapp2

import oauth_token_manager
import tweets
import twitter_fetcher


LISTS_LATEST_KEY_PREFIX = 'list_latest_status_'
LISTS_LATEST_NAMESPACE = 'lists_crawling'

ADMIN_USER = 'martin_cochran'

# Datastore key names
DEFAULT_LISTS_DB_NAME = 'managed_lists_db'
DEFAULT_RECENT_STATUS_DB_NAME = 'most_recent_status_db'

# Maximum number of posts to crawl on any given invocation of /tasks/crawl_list,
# including recrawls.
MAX_POSTS_TO_CRAWL = 1000L

# Num posts to retrieve on each crawl attempt.
POSTS_TO_RETRIEVE = 200L

# Value to indicate that there are no tweets in the stream
FIRST_TWEET_IN_STREAM_ID = 2L


def lists_key(lists_table_name=DEFAULT_LISTS_DB_NAME, user=ADMIN_USER):
  """Constructs a Datastore key for the stored set of managed lists."""
  return ndb.Key('ManagedLists', '%s_%s' % (lists_table_name, user))


class ManagedLists(ndb.Model):
  """A set of list ids that are owned by a given user."""
  list_ids = ndb.StringProperty('l', repeated=True, indexed=False)


class UpdateListsHandler(webapp2.RequestHandler):
  def get(self):
    url = '/tasks/update_lists_rate_limited'
    if self.request.get('fake_data'):
      url = '%s?fake_data=true' % url
      logging.info('Faking the request to update lists')
    taskqueue.add(url=url, method='GET', queue_name='list-lists')
    msg = 'Enqueued rate-limited list update.'
    logging.debug(msg)
    self.response.write(msg)


class UpdateListsRateLimitedHandler(webapp2.RequestHandler):
  """Rate-limited update lists handler via a queue.

  This should never be called directly.  UpdateListsHandler will call this
  handler via a rate-limited queue, which will ensure the twitter API will
  never block requests.
  """
  def get(self):
    """Retrieve the lists via the Twitter API and store them in the datastore."""
    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)

    try:
      json_obj = fetcher.LookupLists(
          ADMIN_USER, fake_data=self.request.get('fake_data'))
    except twitter_fetcher.FetchError as e:
      msg = 'Could not retrieve lists for %s' % ADMIN_USER
      logging.warning('%s: %s', msg, e)
      self.response.write(msg)
      return

    list_objs = json_obj.get('lists', [])
    lists = [k.get('id_str', '') for k in list_objs]

    new_lists = set(lists)
    existing_list_results = ManagedLists.query(ancestor=lists_key()).fetch(1)
    if not existing_list_results:
      existing_list_results = [ManagedLists(parent=lists_key())]

    existing_list = existing_list_results[0]
    old_lists = set(existing_list.list_ids)
    if new_lists == old_lists:
      msg = 'No lists to update: %s' % ','.join(old_lists)
      logging.info(msg)
      self.response.write(msg)
      return

    # Update the db
    existing_list.list_ids = lists
    existing_list.put()

    msg = 'Updated lists for user %s: %s' % (ADMIN_USER, lists)
    logging.info(msg)
    self.response.write(msg)


class CrawlAllListsHandler(webapp2.RequestHandler):
  def get(self):
    admin_list_result = ManagedLists.query(ancestor=lists_key()).fetch(1)
    if not admin_list_result:
      msg = 'No lists to crawl'
      logging.warning(msg)
      self.response.write(msg)
      return

    # For every list, enqueue a task to crawl that list.
    for l in admin_list_result[0].list_ids:
      taskqueue.add(url='/tasks/crawl_list', method='GET',
          params={'list_id': l, 'fake_data': self.request.get('fake_data')},
          queue_name='list-statuses')

    msg = 'Enqueued crawl requests for lists %s' % admin_list_result[0].list_ids
    logging.debug(msg)
    self.response.write(msg)


class CrawlListHandler(webapp2.RequestHandler):
  """Crawls the new statuses from a pre-defined list."""
  def get(self):
    list_id = self.request.get('list_id')
    if not list_id:
      msg = 'No list name specified'
      logging.warning(msg)
      self.response.write(msg)
      return

    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)

    last_tweet_id = self._LookupLatestTweet(list_id)
    since_id = self._ParseLongParam('since_id')
    max_id =  self._ParseLongParam('max_id')
    num_to_crawl = self._ParseLongParam('num_to_crawl')
    if not num_to_crawl:
      num_to_crawl = POSTS_TO_RETRIEVE
    if since_id:
      last_tweet_id = since_id

    # Decrement the last tweet by 1 so that we always get the last
    # tweet in the response.  This is how we know we're caught up in the
    # stream. This is required because the API may not return 'count' number
    # of tweets since it will filter duplicates after retrieving 'count' from
    # the backend.
    last_tweet_id = last_tweet_id - 1

    try:
      json_obj = fetcher.ListStatuses(list_id, count=num_to_crawl,
          since_id=last_tweet_id, max_id=max_id,
          fake_data=self.request.get('fake_data'))
    except twitter_fetcher.FetchError as e:
      msg = 'Could not fetch statuses for list %s' % list_id
      logging.warning('%s: %s', msg, e)
      self.response.write(msg)
      return
    
    # Keep track of the first tweet in the list for bookkeeping purposes.
    latest_incoming_tweet = None
    oldest_incoming_tweet = None
    for json_twt in json_obj:
      twt = tweets.Tweet.getOrInsertFromJson(json_twt, from_list=list_id)
      if not latest_incoming_tweet:
        latest_incoming_tweet = twt
      if not twt:
        # TODO: need to keep track of a counter, fire alert
        logging.warning('Could not parse tweet from %s', json_twt)
        continue
      oldest_incoming_tweet = twt

      tweets.User.getOrInsertFromJson(json_twt.get('user', {}))

    num_crawled = len(json_obj)
    total_crawled = self._ParseLongParam('total_crawled')
    self._PossiblyEnqueueMoreCrawling(list_id, last_tweet_id, oldest_incoming_tweet,
        num_crawled, num_to_crawl, num_crawled + total_crawled)

    # Update the value of most recent tweet.
    self._UpdateLatestTweet(latest_incoming_tweet, list_id)

    logging.info('Added %s tweets to db for list %s', num_crawled, list_id)
    self.response.write('Added %s tweets to db' % num_crawled)

  def _PossiblyEnqueueMoreCrawling(self, list_id, tweet_in_db_id,
      oldest_incoming_tweet, num_tweets_crawled, num_requested, total_crawled):
    """Enqueue more tweet crawling if we haven't processed all stream updates.

    Args:
      list_id: ID of the list being crawled.
      tweet_in_db_id: ID of most recent tweet in the tweet DB.
      oldest_incoming_tweet: lowest-id tweet processed outside the DB.
      num_tweets_crawled: Number of tweets crawled during this crawl attempt.
      num_requested: Number of tweets request
      total_crawled: Total number of tweets crawled during this crawl attempt,
        including repeated calls to enqueue more crawl requests that resulted
        from the original crawl request.
    Returns:
      Any tasks that were enqueued.
    """
    logging.debug('list_id: %s', list_id)
    logging.debug('tweet_in_db_id: %s', tweet_in_db_id)
    logging.debug('num_tweets_crawled: %s', num_tweets_crawled)
    logging.debug('num_requested: %s', num_requested)
    logging.debug('total_crawled: %s', total_crawled)
    # If no tweets were in the stream, then there are no more to crawl.
    if not oldest_incoming_tweet:
      return None
    logging.debug('oldest_incoming_tweet.id_str: %s', oldest_incoming_tweet.id_str)

    # If the oldest tweet returned is the most recent on in the db, then
    # we're all caught up.
    if long(oldest_incoming_tweet.id_str) <= tweet_in_db_id + 1:
      return None

    # If we hit our threshold, bail.
    if total_crawled >= MAX_POSTS_TO_CRAWL:
      return None

    # If this is the first time we've crawled this list, don't worry about it.
    # The user backfill will ensure that we get good enough history for the
    # stream.
    if tweet_in_db_id + 1 == FIRST_TWEET_IN_STREAM_ID:
      return None

    params = {
        'list_id': list_id,
        'total_crawled': total_crawled,
        'max_id': long(oldest_incoming_tweet.id_str),
        'since_id': tweet_in_db_id + 1,
        'num_to_crawl': num_requested,
    }

    logging.info('More tweets in update than fetched - enqueuing another task')
    logging.info('Total crawled: %s, num crawled this iteration: %s',
        total_crawled, num_tweets_crawled)
    return taskqueue.add(url='/tasks/crawl_list', method='GET',
        params=params, queue_name='list-statuses')

  # TODO: consider making this and other datastore writes in this function
  # transactional to be more resilient to errors / bugs / API service outages.
  # Writing all tweets in one transaction using an ancestor query is the way
  # to go.
  # https://cloud.google.com/appengine/docs/python/ndb/transactions
  def _UpdateLatestTweet(self, latest_tweet, list_id):
    """Update the 'latest' table with the most recent set of tweets.

    Args:
      latest_tweet: Most recent tweet in the stream to be indexed.
      list_id: ID of the list.
    """
    if not latest_tweet:
      logging.debug('No latest tweet added')
      return

    latest_id = self._LookupLatestTweet(list_id)

    if long(latest_tweet.id_str) < latest_id:
      logging.warning('Tweet %s written to the datastore older than latest %s',
          latest_tweet.id_str, latest_id)
      return

    # Update memcache
    memcache.add(key=LISTS_LATEST_KEY_PREFIX + list_id,
        value=long(latest_tweet.id_str), time=3600, namespace=LISTS_LATEST_NAMESPACE)

  def _LookupLatestTweet(self, list_id):
    """Lookup the most recent tweet in the db for the given list.

    Args:
      list_id: The ID of the list.
    Returns:
      long(tweet.id_str) for the latest 'tweet' in db for that list.
    """
    # This won't necessarily be consistent, but we will never double-write
    # tweets since we call get_or_insert.
    cache_latest = memcache.get(
        key=LISTS_LATEST_KEY_PREFIX + list_id, namespace=LISTS_LATEST_NAMESPACE)

    # TODO: remove once transitioned to using integer IDs instead of string and
    # this has been deployed.
    if type(cache_latest) == long:
      return cache_latest

    # Let's look at the datastore
    tweet_query = tweets.Tweet.query(tweets.Tweet.from_list == list_id).order(
        -tweets.Tweet.id_str)

    twts = tweet_query.fetch(1)
    if twts:
      return long(twts[0].id_str)

    return FIRST_TWEET_IN_STREAM_ID
 
  def _ParseLongParam(self, param_name, default_value=0L):
    """Parse and return a parameter as an integer.

    Args:
      param_name: The name of the parameter.
      default_value: Long default value to return.
    Returns:
      The parsed integer value, or the default value if it cannot be parsed.
    """
    try:
      return long(self.request.get(param_name, default_value=str(default_value)))
    except ValueError as e:
      logging.debug('Could not parse value for param %s, value %s, default %s',
          param_name, self.request.get(param_name), default_value)
      return default_value


app = webapp2.WSGIApplication([
  ('/tasks/update_lists', UpdateListsHandler),
  ('/tasks/update_lists_rate_limited', UpdateListsRateLimitedHandler),
  ('/tasks/crawl_list', CrawlListHandler),
  ('/tasks/crawl_all_lists', CrawlAllListsHandler),
], debug=True)
