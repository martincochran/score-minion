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

import jinja2
import webapp2

import oauth_token_manager
import tweet_util
import tweets
import twitter_fetcher
import user_util


LISTS_LATEST_KEY_PREFIX = 'list_latest_status_'
LISTS_LATEST_NAMESPACE = 'lists_crawling'

ADMIN_USER = 'martin_cochran'

# Datastore key names
DEFAULT_LISTS_DB_NAME = 'managed_lists_db'
DEFAULT_RECENT_STATUS_DB_NAME = 'most_recent_status_db'


def lists_key(lists_table_name=DEFAULT_LISTS_DB_NAME, user=ADMIN_USER):
  """Constructs a Datastore key for the stored set of managed lists."""
  return ndb.Key('ManagedLists', '%s_%s' % (lists_table_name, user))


class ManagedLists(ndb.Model):
  """A set of list ids that are owned by a given user."""
  list_ids = ndb.StringProperty('l', repeated=True, indexed=False)


class UpdateListsHandler(webapp2.RequestHandler):
  def get(self):
    taskqueue.add(url='/tasks/update_lists_rate_limited', method='GET',
        queue_name='list-lists')
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
      json_obj = fetcher.LookupLists(ADMIN_USER)
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
      msg = 'No lists to update'
      logging.debug(msg)
      self.response.write(msg)
      return

    # Update the db
    existing_list.list_ids = lists
    existing_list.put()

    msg = 'Updated lists for user %s: %s' % (ADMIN_USER, lists)
    logging.debug(msg)
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
          params={'list_id': l}, queue_name='list-statuses')

    msg = 'Enqueued crawl requests for lists %s' % admin_list_result[0].list_ids
    logging.debug(msg)
    self.response.write(msg)


class CrawlListHandler(webapp2.RequestHandler):
  """Crawls the new statuses from a pre-defined list."""
  def get(self):
    # TODO: this will only index the first 100, and will miss some updates if
    # there were more in a given window (though right now it's unlikely for 1
    # minute crawling intervals).  Improve to crawl a greater number of items
    # up to a threshold.
    list_id = self.request.get('list_id')
    if not list_id:
      msg = 'No list name specified'
      logging.warning(msg)
      self.response.write(msg)
      return

    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)

    try:
      json_obj = fetcher.ListStatuses(list_id)
    except twitter_fetcher.FetchError as e:
      msg = 'Could not fetch statuses for list %s' % list_id
      logging.warning('%s: %s', msg, e)
      self.response.write(msg)
      return

    last_tweet, last_created_at = self._LookupLatestTweet(list_id)

    parsed_tweets = []
    for json_twt in json_obj:
      twt = tweets.Tweet.fromJson(json_twt)
      if not twt:
        logging.warning('Could not parse tweet from %s', json_twt)
        continue

      if self._HaveSeenTweetBefore(twt.id_str, twt.created_at,
          last_tweet, last_created_at):
        # We've seen this tweet before, which means we're caught up in the
        # stream.  No need to continue
        logging.info('Caught up to indexed stream at status id %s', twt.id_str)
        break

      # Add this list ID to the tweet for bookkeeping purposes.
      twt.from_list = list_id
      parsed_tweets.append(twt)
      user_util.QueryAndSetUser(tweets.User.fromJson(json_twt.get('user', {})))

    num_tweets_added = len(parsed_tweets)
    for tweet in parsed_tweets:
      logging.info('Adding tweet %s', tweet.id_str)
      tweet_util.QueryAndSetTweet(tweet)

    # Update the value of most recent tweet.
    self._UpdateLatestTweet(parsed_tweets, list_id)

    self.response.write('Added %s tweets to db' % num_tweets_added)

  def _HaveSeenTweetBefore(self, tweet_id, created_at,
      latest_tweet_id, latest_created_at):
    """Returns true if we've processed this tweet before.

    We optimize this for speed and to minimize DB lookups.  Tweet IDs are
    generally increasing, but are not guaranteed to be monotonically increasing,
    so we need to check the creation date in addition to the id, though the
    ID should be enough in almost all cases.
    """
    # This will be the common case - we catch up the to stream with a tweet
    # we've seen before.
    logging.info('tweet ids: %s %s', tweet_id, latest_tweet_id)
    if tweet_id == latest_tweet_id:
      return True

    # If there are no tweets in the datastore for the list, then we haven't seen
    # it before.
    if (not latest_tweet_id) or (not latest_created_at):
      return False

    if tweet_id > latest_tweet_id and created_at > latest_created_at:
      return False

    if tweet_id < latest_tweet_id and created_at < latest_created_at:
      return True

    # Now we're in grey area where the created_at date is the same, which
    # should be very rare. Twitter generates the last few bits randomly, so we
    # also cannot rely on the value of the tweet id.
    #
    # In this case we do a datastore lookup.
    tweet_query = tweets.Tweet.query(ancestor=tweets.tweet_key(tweet_id))
    if tweet_query.fetch(1):
      return True

    return False

  # TODO: consider making this and other datastore writes in this function
  # transactional to be more resilient to errors / bugs / API service outages.
  # https://cloud.google.com/appengine/docs/python/ndb/transactions
  def _UpdateLatestTweet(self, tweets_added, list_id):
    """Update the 'latest' table with the most recent set of tweets.

    Args:
      tweets_added: Set of tweets that were written to the datastore for the given list,
        sorted in order of decreasing status ids.
      list_id: ID of the list.
    """
    if not tweets_added:
      return

    latest_id, latest_created_at = self._LookupLatestTweet(list_id)

    # Let's not make life hard for ourselves - the most recent tweet is the
    # first returned from the API.
    most_recent_tweet = tweets_added[0]

    if most_recent_tweet.id_str < latest_id:
      logging.warning('Tweet %s written to the datastore older than latest %s',
          most_recent_tweet.id_str, latest_id)
      return

    # Update memcache
    memcache.add(key=LISTS_LATEST_KEY_PREFIX + list_id,
        value=(most_recent_tweet.id_str, most_recent_tweet.created_at),
        time=3600, namespace=LISTS_LATEST_NAMESPACE)

  def _LookupLatestTweet(self, list_id):
    """Lookup the most recent tweet in the db for the given list.

    Args:
      list_id: The ID of the list.
    Returns:
      Pair of (tweet.id_str, tweet.created_at) date for the latest 'tweet' in db for that list.
    """
    # This is a little tricky since we're not using ancestor queries and a consistent datastore
    cache_latest = memcache.get(
        key=LISTS_LATEST_KEY_PREFIX + list_id, namespace=LISTS_LATEST_NAMESPACE)
    if cache_latest:
      return cache_latest

    # Let's look at the datastore
    tweet_query = tweets.Tweet.query(tweets.Tweet.from_list == list_id).order(
        -tweets.Tweet.id_str)

    twts = tweet_query.fetch(1)
    if twts:
      return (twts[0].id_str, twts[0].created_at)

    return (None, None)


app = webapp2.WSGIApplication([
  ('/tasks/update_lists', UpdateListsHandler),
  ('/tasks/update_lists_rate_limited', UpdateListsRateLimitedHandler),
  ('/tasks/crawl_list', CrawlListHandler),
  ('/tasks/crawl_all_lists', CrawlAllListsHandler),
], debug=True)
