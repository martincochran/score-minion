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

from datetime import datetime, timedelta
import logging
import math
import os

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from game_model import Game
from game_model import GameSource
from game_model import Team
from scores_messages import AgeBracket
from scores_messages import Division
from scores_messages import League

import webapp2

import list_id_bimap
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

# Maximum number of total requests that can be made in a crawl attempt of a list,
# including all recrawls.
MAX_REQUESTS = 10L

# Num posts to retrieve on each crawl attempt.
POSTS_TO_RETRIEVE = 200L

# Value to indicate that there are no tweets in the stream
FIRST_TWEET_IN_STREAM_ID = 2L

# Threshold for consistency score where we add a tweet to a game instead of
# creating a new one.
GAME_CONSISTENCY_THRESHOLD = 1.0

# Maximum users per user crawl request.
MAX_USERS_PER_CRAWL_REQUEST = 100

UNKNOWN_SR_ID = 'unknown_id'

MAX_LENGTH_OF_GAME_IN_HOURS = 5


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


class CrawlState():
  """Contains all data about the state of the crawl for a given list."""

  def __init__(self, list_id, total_crawled, max_id, total_requests_made,
      num_to_crawl, last_tweet_id):
    """Initializes the CrawlState with data about the crawl.

    Args:
      list_id: List ID requested to be crawled.
      total_crawled: Total # of tweets crawled so far, including recrawls.
      max_id: Maximum ID to crawl, which is passed to the Twitter API when
        further requests are triggered. It's an optimization so the API will
        only return tweets with an ID lower than that.
      total_requests_made: Total # of API requests made during this crawl cycle
        for this list.
      num_to_crawl: Maximum number of tweets to crawl this cycle across all API
        requests
      last_tweet_id: Minimum ID to crawl, which is passed to the Twitter API as an
        optimization to only return tweets with an ID higher than that.
    """
    self.list_id = list_id
    self.total_crawled = total_crawled
    self.max_id = max_id
    self.total_requests_made = total_requests_made
    self.num_to_crawl = num_to_crawl or POSTS_TO_RETRIEVE

    # Decrement the last tweet by 1 so that we always get the last
    # tweet in the response.  This is how we know we're caught up in the
    # stream. This is required because the API may not return 'count' number
    # of tweets since it will filter duplicates after retrieving 'count' from
    # the backend.
    self.last_tweet_id = last_tweet_id - 1

  @classmethod
  def FromRequest(cls, request, last_tweet_id):
    """Initialize the crawl state from the webapp2 request.

    Args:
      request: webapp2 request object
      last_tweet_id: Last tweet ID crawled for this list.
    Returns:
      A CrawlState object initialized with fields from the parameters
      encoded in the request.
    """
    since_id = CrawlState._ParseLongParam(request, 'since_id')
    if since_id:
      last_tweet_id = since_id
    return CrawlState(
        request.get('list_id'),
        CrawlState._ParseLongParam(request, 'total_crawled'),
        CrawlState._ParseLongParam(request, 'max_id'),
        CrawlState._ParseLongParam(request, 'total_requests_made'),
        CrawlState._ParseLongParam(request, 'num_to_crawl'),
        last_tweet_id)

  @classmethod
  def _ParseLongParam(cls, request, param_name, default_value=0L):
    """Parse and return a parameter as an integer.

    Args:
      request: incoming request object
      param_name: The name of the parameter.
      default_value: Long default value to return.
    Returns:
      The parsed integer value, or the default value if it cannot be parsed.
    """
    try:
      return long(request.get(param_name, default_value=str(default_value)))
    except ValueError as e:
      logging.debug('Could not parse value for param %s, value %s, default %s',
          param_name, request.get(param_name), default_value)
      return default_value


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


class BackfillGamesHandler(webapp2.RequestHandler):
  """Handler to update prior games / do data cleanup."""
  def get(self):
    """Adds backfill requests to the crawl queue."""
    admin_list_result = ManagedLists.query(ancestor=lists_key()).fetch(1)
    if not admin_list_result:
      msg = 'No lists to backfill'
      logging.warning(msg)
      self.response.write(msg)
      return

    duration = self._ParseDuration(self.request.get('duration'))
    if not duration:
      msg = 'Invalid duration format. Examples: "3w", "4m"'
      logging.warning(msg)
      self.response.write(msg)
      return

    start_date = ParseDate(self.request.get('start_date'))
    if self.request.get('start_date') and not start_date:
      msg = 'Invalid start_date format. Example: "11/16/2014"'
      logging.warning(msg)
      self.response.write(msg)
      return
    if not start_date:
      start_date = datetime.utcnow()

    backfill_dates = self._GenerateBackfillDates(duration, start_date)
    # For every list, enqueue a task to crawl that list.
    for l in admin_list_result[0].list_ids:
      for backfill_date in backfill_dates:
        taskqueue.add(url='/tasks/crawl_list', method='GET',
            params={
                'list_id': l,
                'backfill_date': backfill_date.strftime(DATE_PARSE_STRF)
            },
            queue_name='game-backfill')

    msg = 'Enqueued backfill requests for lists %s for dates %s' % (
        admin_list_result[0].list_ids, backfill_dates)
    logging.debug(msg)
    self.response.write(msg)

  def _GenerateBackfillDates(self, duration, start_date):
    """Generates target dates for a week's worth of backfill.

    Args:
      duration: timedelta object
      start_date: date backfill should start
    Returns:
      A list of datetime objects at weekly increments, Wednesday to Tuesday,
      starting before the start_date and ending before start_date - duration.
    """
    # First find the nearest Wednesday before the start.
    crawl_date = start_date - timedelta(days=((start_date.weekday() + 5) % 7))
    days = []
    while crawl_date > start_date - duration:
      days.append(crawl_date)
      crawl_date = crawl_date - timedelta(weeks=1)
    return days

  def _ParseDuration(self, duration_param):
    """Parses the duration from the request parameter.

    Args:
      duration_param: Parameter from the request object

    Returns:
      A timedelta object if the param could be successfully parsed.
    """
    if not duration_param:
      return None
    if duration_param[-1] not in ['w', 'm']:
      return None
    unit = duration_param[-1]
    try:
      num = int(duration_param[:-1])
    except ValueError as e:
      logging.error('Could not parse duration parameter: %s', e)
      return None
    if num < 1:
      logging.error('Non-positive duration specified: %d', num)
      return None
    if unit == 'w':
      if num > 26:
        logging.error('Backfill period too long: %d weeks', num)
        return None
      return timedelta(weeks=num)
    else:
      if num > 6:
        logging.error('Backfill period too long: %d months', num)
        return None
      return timedelta(weeks=4*num)


DATE_PARSE_STRF = '%m/%d/%Y'


def ParseDate(date_param):
  """Parses a date from the request parameter.

  Args:
    date_param: Parameter from the request object

  Returns:
    A datetime object if the param could be successfully parsed.
  """
  try:
    return datetime.strptime(date_param, DATE_PARSE_STRF)
  except ValueError as e:
    logging.debug('Failed to parse date from param')
    return None


class CrawlAllUsersHandler(webapp2.RequestHandler):
  """Handler to rate-list enqueue crawling for all known users."""
  def get(self):
    users_list_result = tweets.User.query().fetch()
    if not users_list_result:
      msg = 'No users to crawl'
      logging.warning(msg)
      self.response.write(msg)
      return

    user_ids = set()

    # For every user, put the id_str into a set. This will ensure only one
    # crawl request is made even if there are multiple user objects for a
    # given ID str.
    for user in users_list_result:
      user_ids.add(user.id_str)

    # This makes testing easier.
    sorted_user_ids = sorted(user_ids)
    crawl_user_set = []
    for user_id in sorted_user_ids:
      crawl_user_set.append(user_id)
      if len(crawl_user_set) >= MAX_USERS_PER_CRAWL_REQUEST:
        taskqueue.add(url='/tasks/crawl_users', method='POST',
            params={'user_id': ','.join(crawl_user_set)},
            queue_name='lookup-users')
        crawl_user_set = []

    # Request all the remaining ids.
    if crawl_user_set:
      taskqueue.add(url='/tasks/crawl_users', method='POST',
          params={'user_id': ','.join(crawl_user_set)},
          queue_name='lookup-users')

    msg = 'Enqueued crawl requests for users %s' % ', '.join(sorted(user_ids))
    logging.debug(msg)
    self.response.write(msg)


class CrawlUserHandler(webapp2.RequestHandler):
  """Handler to update twitter user information for multiple users."""
  def post(self):
    user_id_param = self.request.get('user_id')
    if not user_id_param:
      msg = 'No user id specified'
      logging.warning(msg)
      self.response.write(msg)
      return

    # Assumption is user_id_param is a comma-separated list of
    # user ids as specified at
    # https://dev.twitter.com/rest/reference/get/users/lookup
    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)

    try:
      json_obj = fetcher.LookupUsers(user_id_param)
    except twitter_fetcher.FetchError as e:
      msg = 'Could not lookup users %s' % user_id_param
      logging.warning('%s: %s', msg, e)
      self.response.write(msg)

    for json_user in json_obj:
      # TODO: refactor into separate method
      model_user = tweets.User.getOrInsertFromJson(json_user)
      json_user_url = json_user.get('profile_image_url_https', '')
      # Update the user profile URL if it has changed.
      if model_user and model_user.profile_image_url_https != json_user_url:
        model_user.profile_image_url_https = json_user_url
        model_user.put()

      # Clean-up: only need to do once on production data.
      # TODO: delete after the one-time clean-up
      # Lookup all users with that ID.
      user_query = tweets.User.query(
          tweets.User.id_str == json_user.get('id_str', ''))
      all_users = user_query.fetch()
      for user in all_users:
        if user.key != model_user.key:
          logging.info('Deleting extra user: %s', user.screen_name)
          user.key.delete()
 

class CrawlListHandler(webapp2.RequestHandler):
  """Crawls the new statuses from a pre-defined list."""
  def get(self):
    list_id = self.request.get('list_id')
    if not list_id:
      msg = 'No list name specified'
      logging.warning(msg)
      self.response.write(msg)
      return

    last_tweet_id = self._LookupLatestTweet(list_id)
    crawl_state = CrawlState.FromRequest(self.request, last_tweet_id)
    
    # In parallel: look-up the latest set of games for this
    # division and cache it
    division, age_bracket, league = list_id_bimap.ListIdBiMap.GetStructuredPropertiesForList(
        crawl_state.list_id)

    backfill_date = ParseDate(self.request.get('backfill_date'))
    games_start = datetime.utcnow()
    if backfill_date:
      games_start = backfill_date + timedelta(weeks=1)
      # Query tweets for that week for this list
      tweet_query = tweets.Tweet.query(
          tweets.Tweet.from_list == list_id,
          tweets.Tweet.created_at > games_start - timedelta(weeks=1),
          tweets.Tweet.created_at < games_start).order(
          ).order(-tweets.Tweet.created_at)
      twts_future = tweet_query.fetch_async()

    # Only pull up games for the last two weeks.
    # TODO: run a separate query for games populated from score reporter, which
    # may have been created weeks before the actual game.
    games_query = Game.query(Game.division == division,
        Game.age_bracket == age_bracket,
        Game.league == league,
        Game.last_modified_at > games_start - timedelta(weeks=1),
        Game.last_modified_at < games_start).order(
            -Game.last_modified_at)
    games_future = games_query.fetch_async()

    if not backfill_date:
      token_manager = oauth_token_manager.OauthTokenManager()
      fetcher = twitter_fetcher.TwitterFetcher(token_manager)
      try:
        json_obj = fetcher.ListStatuses(crawl_state.list_id, count=crawl_state.num_to_crawl,
            since_id=crawl_state.last_tweet_id, max_id=crawl_state.max_id,
            fake_data=self.request.get('fake_data'))
      except twitter_fetcher.FetchError as e:
        msg = 'Could not fetch statuses for list %s' % crawl_state.list_id
        logging.warning('%s: %s', msg, e)
        self.response.write(msg)

        # TODO: retry the request a fixed # of times
        return

      # Update the various datastores.
      twts, users = self.UpdateTweetDbWithNewTweets(json_obj, crawl_state)

    if backfill_date:
      twts = twts_future.get_result()
      users = {}

    existing_games = games_future.get_result()
    self.UpdateGames(twts, existing_games, users, division, age_bracket, league)
    # TODO(NEXT): Consider merging the games if they are appropriately consistent.

  def UpdateTweetDbWithNewTweets(self, json_obj, crawl_state):
    """Update the Tweet DB with the newly-fetched tweets.

    Args:
      json_obj: The parsed JSON object from the API response.
      crawl_state: State of the crawl for this list.
    Returns:
      A 2-tuple. The first item is the list of tweets.Tweet objects that were
      added to the datastore and the second is a dictionary mapping string
      user ids to the tweets.User objects for all authors of tweets in this
      crawl cycle.
    """
    # TODO: If a user is new this cycle and more crawling is enqueued, the
    # team might not be populated. The Game creation code should look up
    # users with the key that guarantees consistency instead of doing a search.

    # Keep track of the first tweet in the list for bookkeeping purposes.
    latest_incoming_tweet = None
    oldest_incoming_tweet = None
    twts = []
    users = {}
    for json_twt in json_obj:
      # TODO: consider writing all of these at the same time / in one transaction, possibly
      # in the same transaction that updates all the games as well.
      twt = tweets.Tweet.getOrInsertFromJson(json_twt,
          from_list=crawl_state.list_id)
      if not latest_incoming_tweet:
        latest_incoming_tweet = twt
      if not twt:
        # TODO: need to keep track of a counter, fire alert
        logging.warning('Could not parse tweet from %s', json_twt)
        continue

      model_user = tweets.User.getOrInsertFromJson(json_twt.get('user', {}))
      json_user_url = json_twt.get('user', {}).get(
          'profile_image_url_https', '')
      # Update the user profile URL if it has changed.
      if model_user and model_user.profile_image_url_https != json_user_url:
        model_user.profile_image_url_https = json_user_url
        model_user.put()
      if model_user and not users.get(model_user.id_str, None):
        users[model_user.id_str] = model_user

      oldest_incoming_tweet = twt
      twts.append(twt)

    num_crawled = len(json_obj)
    self._PossiblyEnqueueMoreCrawling(crawl_state.list_id,
        crawl_state.last_tweet_id, oldest_incoming_tweet,
        num_crawled, crawl_state.num_to_crawl,
        num_crawled + crawl_state.total_crawled,
        crawl_state.total_requests_made + 1)

    # Update the value of most recent tweet.
    self._UpdateLatestTweet(latest_incoming_tweet, crawl_state.list_id)

    logging.info('Added %s tweets to db for list %s', num_crawled,
        crawl_state.list_id)
    self.response.write('Added %s tweets to db' % num_crawled)
 
    return (twts, users)

  def UpdateGames(self, twts, existing_games, users, division, age_bracket,
      league):
    """Update the datastore with the game information in the given tweets.

    Args:
      twts: list of tweets.Tweet objects
      existing_games: list of game_model.Game objects already in the datastore
      users: dictionary from user ids to tweets.User objects for authors of all
        the tweets in twts
      division: Division of tweets
      age_bracket: AgeBracket of tweets
      league: League of tweets
    """
    # This will keep track of games added during processing of these tweets.
    added_games = []

    logging.info('UpdateGames: %d tweets, %d existing games',
        len(twts), len(existing_games))
    for twt in twts:
      self._PossiblyAddTweetToGame(twt, existing_games, added_games, users,
          division, age_bracket, league)

    # Update the games
    # TOOD: consider doing this in one transaction to save time
    for game in existing_games + added_games:
      game.put()

  def _PossiblyEnqueueMoreCrawling(self, list_id, tweet_in_db_id,
      oldest_incoming_tweet, num_tweets_crawled, num_requested, total_crawled,
      total_requests_made):
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
      total_requests_made: Total number of requests made trying to crawl this
        list.
    Returns:
      Any tasks that were enqueued.
    """
    logging.debug('list_id: %s', list_id)
    logging.debug('tweet_in_db_id: %s', tweet_in_db_id)
    logging.debug('num_tweets_crawled: %s', num_tweets_crawled)
    logging.debug('num_requested: %s', num_requested)
    logging.debug('total_crawled: %s', total_crawled)
    logging.debug('total_requests_made: %s', total_requests_made)
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

    # Don't crawl more if we only crawled one this turn. This works around a
    # behavior of the Twitter API that appears to cap the number of historical
    # tweets you can retrieve from a given list.
    if num_tweets_crawled <= 1:
      logging.info('Only 1 tweet crawled this iteration - stopping backfill')
      return None

    if total_requests_made >= MAX_REQUESTS:
      logging.info('Backfill reached limit of %s total API requests',
          MAX_REQUESTS)
      return None

    params = {
        'list_id': list_id,
        'total_crawled': total_crawled,
        'max_id': long(oldest_incoming_tweet.id_str),
        'since_id': tweet_in_db_id + 1,
        'num_to_crawl': num_requested,
        'total_requests_made': total_requests_made,
    }

    logging.info('More tweets in update than fetched - enqueuing another task')
    logging.info('Total crawled: %s, num crawled this iteration: %s',
        total_crawled, num_tweets_crawled)
    return taskqueue.add(url='/tasks/crawl_list', method='GET',
        params=params, queue_name='list-statuses')

  def _PossiblyAddTweetToGame(self, twt, existing_games, added_games, user_map,
      division, age_bracket, league):
    """Determine if a tweet is a game tweet and add it to a game if so.

    Args:
      twt: tweets.Tweet object to be processed.
      existing_games: list of game_model.Game objects that are currently in the
        db.
      added_games: list of game_model.Game objects that have been added as part 
        of this crawl request.
      user_map: map of string user ids to users which have authored a tweet
        during this crawl cycle and thus may not be propagated in the db yet.
      division: Division to set new Game to, if creating one
      age_bracket: AgeBracket to set new Game to, if creating one
      league: League to set new Game to, if creating one
    """
    if not twt:
      return
    if not twt.two_or_more_integers:
      return

    score_indicies = self._FindScoreIndicies(twt.entities.integers, twt.text)
    if not score_indicies:
      logging.debug('Ignoring tweet - numbers aren\'t scores: %s', twt.text)
      return

    teams = self._FindTeamsInTweet(twt, user_map)
    scores = [twt.entities.integers[score_indicies[0]].num,
          twt.entities.integers[score_indicies[1]].num]
    (consistency_score, game) = self._FindMostConsistentGame(
        twt, existing_games, added_games, teams, division, age_bracket, league)

    # Try to find a game that matches this tweet in existing games. If no such
    # game exists, create one.
    if consistency_score < GAME_CONSISTENCY_THRESHOLD:
      added_games.append(Game.FromTweet(twt, teams, scores, division,
        age_bracket, league))
    else:
      for source in game.sources:
        if twt.id_64 == source.tweet_id:
          logging.debug('Tried to add tweet more than once as game source %s',
              twt)
          return
      game.sources.append(GameSource.FromTweet(twt))
      game.sources.sort(cmp=lambda x,y: cmp(y.update_date_time,
        x.update_date_time))
      self._MergeTeamsIntoGame(game, teams)

  def _FindMostConsistentGame(self, twt, existing_games, added_games, teams,
      division, age_bracket, league):
    """Returns the game most consistent with the given games.

    If no game is found to be at all consistent, the consistency score returned
    will be 0.0 and the matching game will be None. existing_games and
    added_games should be pre-filtered to contain only those games with the
    correct domain, age bracket, and league.

    Args:
      twt: tweets.Tweet object to be processed.
      existing_games: list of game_model.Game objects that are currently in the
        db.
      added_games: list of game_model.Game objects that have been added as part 
        of this crawl request.
      teams: list of game_model.Team objects involved in this game.
      division: Division to set new Game to, if creating one
      age_bracket: AgeBracket to set new Game to, if creating one
      league: League to set new Game to, if creating one

    Returns:
      A (score, game) pair of the game that matches mostly closely with the
      tweet as well as a confidence score in the match.
    """
    for game in existing_games + added_games:
      for game_team in game.teams:
        for tweet_team in teams:
          if game_team.twitter_id != tweet_team.twitter_id:
            continue
          if game_team.twitter_id == None and game_team.score_reporter_id == UNKNOWN_SR_ID:
            logging.debug('No useful identifier found for game team %s', game_team)
          if tweet_team.twitter_id == None and tweet_team.score_reporter_id == UNKNOWN_SR_ID:
            logging.debug('No useful identifier found for tweet_team %s', tweet_team)
            continue

          # So one of the teams is the same. If this game happened within the last few
          # hours it's probably the same game.
          # TODO(NEXT): do something more sophisticated based on the score updates in the game.
          # eg, even if the tweet already exists in some game this might add it again.
          max_game_length = timedelta(hours=MAX_LENGTH_OF_GAME_IN_HOURS)
          if abs(twt.created_at - game.last_modified_at) < max_game_length:
            return (1.0, game)
        
    return (0.0, None)

  def _FindTeamsInTweet(self, twt, user_map):
    """Find the teams this tweet refers to.

    Determine the two teams this twt is referring to. Currently this only
    works for tweets where one of the authors is one team and only one
    game score is included in the tweet text. Sorry, Ultiworld :)

    Args:
      twt: tweets.Tweet object
      user_map: map from string user ids to users who have authored a tweet
        during this crawl cycle.
    Returns:
      A list of exactly two game_model.Team objects. If the teams cannot be
      determined then the team.score_reporter_id will be set to UNKNOWN_SR_ID
      and no other object properties will be set.
    """
    this_team = self._TeamFromAuthorId(twt.author_id, user_map)

    # TODO: add logic to handle the case where the author of the tweet is not
    # involved in the game.

    # Try to determine the other team based on user account mention.
    other_team = Team(score_reporter_id=UNKNOWN_SR_ID)
    if twt.entities and twt.entities.user_mentions:
      # If there is only one user mention and it's in the db, then likelihood is
      # high that it's the other team.
      if len(twt.entities.user_mentions) == 1:
        other_team = self._TeamFromAuthorId(
            twt.entities.user_mentions[0].user_id, user_map)

    # TODO(NEXT): double-check that this is a team from the same division and
    # age bracket, and league.
    return [this_team, other_team]

  def _TeamFromAuthorId(self, author_id, user_map):
    """Try to build a game_model.Team object from a string user_id.

    Args:
      author_id: (string) twitter ID of the user account.
      user_map: map from string user ids to users who have authored a tweet
        during this crawl cycle.
    Returns:
      A game_model.Team object.  If the user ID is not found in the provided
      user_map or the db then a user with score_reporter_id equal to
      UNKNOWN_SR_ID is returned.
    """
    if user_map.get(author_id):
      return Team.FromTwitterUser(user_map.get(author_id))

    # TODO: lookup user name using memcache
    account_query = tweets.User.query().order(tweets.User.screen_name)
    account_query = account_query.filter(tweets.User.id_str == author_id)
    user = account_query.fetch(1)
    if user:
      return Team.FromTwitterUser(user[0])
    return Team(score_reporter_id=UNKNOWN_SR_ID)

  def _MergeTeamsIntoGame(self, game, teams):
    """Merge the teams from the tweet into the game.

    This is intended to handle the case where a tweet mentions another
    team for the first time.

    Precondition: At least one of the teams in games.teams and teams is
    the same.

    Returns:
      Nothing
    """ 
    if not game.teams:
      game.teams = teams
      return

    # If there are only two teams in the game and one hasn't been identified,
    # then use the teams parsed from the tweet.
    if len(game.teams) == 2:
      for team in game.teams:
        if team.score_reporter_id == UNKNOWN_SR_ID:
          game.teams = teams
          return

    # TODO: consider adding more than two teams to a game and then adding a
    # second pass to determine which of the two mentioned teams are most
    # likely to be the two teams in the game. It's possible for a team to
    # be mentioned at some point during a game, but not a team involved in the
    # game, to be tagged incorrectly as "the" team in the game.

  def _FindScoreIndicies(self, integer_entities, tweet_text):
    """Return the two integer entities referring to the score.

    Args:
      integer_entities: a list of tweets.IntegerEntity objects.
      tweet_text: Tweet text for logging purposes.

    Returns:
      The indicies of the objects referring to the scores, or an empty list if
      there are no suitable indicies.
    """
    for i in range(len(integer_entities) - 1):
      entA = integer_entities[i]
      entB = integer_entities[i+1]
      # For now, be very restrictive: only two integers who are close to one
      # another.
      if math.fabs(entA.end_idx - entB.start_idx) > 4.0:
        logging.debug('Integers too far apart: %s', tweet_text)
        continue
      # The score can't be too high. Some AUDL / MLU games might go to 
      # high scores if there are multiple overtimes.
      if entA.num + entB.num > 100:
        logging.debug('Numbers sum to too high of a number: %s', tweet_text)
        continue
      if tweet_text[entA.end_idx:entB.start_idx].find('-') != -1:
        return [i, i+1]
      logging.debug('Could not find "-" in tweet text: %s', tweet_text)
    # TODO: need to do something more sophisticated for this tweets with multiple
    # games.
    return []

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
  
 
app = webapp2.WSGIApplication([
  ('/tasks/update_lists', UpdateListsHandler),
  ('/tasks/update_lists_rate_limited', UpdateListsRateLimitedHandler),
  ('/tasks/backfill_games', BackfillGamesHandler),
  ('/tasks/crawl_list', CrawlListHandler),
  ('/tasks/crawl_all_lists', CrawlAllListsHandler),
  ('/tasks/crawl_users', CrawlUserHandler),
  ('/tasks/crawl_all_users', CrawlAllUsersHandler),
], debug=True)
