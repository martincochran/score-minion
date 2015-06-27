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
import endpoints
import logging
import math
import uuid

from protorpc import remote

from google.appengine.api import app_identity
from google.appengine.api import taskqueue

from scores_messages import AgeBracket
from scores_messages import Division
from scores_messages import Game
from scores_messages import GameInfoRequest
from scores_messages import GameInfoResponse
from scores_messages import GameSource
from scores_messages import GameSourceType
from scores_messages import GameStatus
from scores_messages import GamesRequest
from scores_messages import GamesResponse
from scores_messages import League
from scores_messages import Team
from scores_messages import TwitterAccount

import tweets

MAX_HOURS_CRAWL_LATENCY = 1

# Client ID for testing
WEB_CLIENT_ID = '245407672402-oisb05fsubs9l96jfdfhn4tnmju4efqe.apps.googleusercontent.com'

# TODO: add Android client ID

# Simple data structure to lookup lists if the league, division, and age
# bracket were specified in the request.
LIST_ID_MAP = {
    League.USAU: {
      Division.OPEN: {
        AgeBracket.COLLEGE: '186814318',
        AgeBracket.NO_RESTRICTION: '186732484',
      },
      Division.WOMENS: {
        AgeBracket.COLLEGE: '186814882',
        AgeBracket.NO_RESTRICTION: '186732631',
      },
      Division.MIXED: {
        AgeBracket.NO_RESTRICTION: '186815046',
      },
    },
    League.AUDL: {
      Division.OPEN: {
        AgeBracket.NO_RESTRICTION: '186926608',
      },
    },
    League.MLU: {
      Division.OPEN: {
        AgeBracket.NO_RESTRICTION: '186926651',
      },
    },
}


@endpoints.api(name='scores', version='v1',
               description='Score Minion API')
               #allowed_client_ids=[WEB_CLIENT_ID, endpoints.API_EXPLORER_CLIENT_ID])
               #auth_level=AUTH_LEVEL.OPTIONAL)
class ScoresApi(remote.Service):
  """Class which defines Score Minion API v1."""

  @staticmethod
  def _LookupMatchingTweets(request, num=100):
    """Returns a set of tweets from the DB matching the request criteria.

    Args:
      request: GamesRequest object specifying what games to look up
      num: Number of tweets to retrieve from the DB

    Returns:
      The list of Tweet objects that match the criteria.
    """
    # Currently the only request filter is by division.
    # TODO: support other filters (by tournament, eg) and relax requirement
    # that division, league, and age must be specified.
    list_id = ScoresApi._LookupListFromDivisionAgeAndLeague(
        request.division, request.age_bracket, request.league)
    if not list_id:
      logging.info('No list id found from GamesRequest')
      return []

    logging.info('Found list id %s from request %s', list_id, request)

    tweet_query = tweets.Tweet.query().order(-tweets.Tweet.created_at)
    tweet_query = tweet_query.filter(tweets.Tweet.two_or_more_integers == True)
    tweet_query = tweet_query.filter(tweets.Tweet.from_list == list_id)

    return tweet_query.fetch(num)

  @staticmethod
  def _LookupListFromDivisionAgeAndLeague(division, age_bracket, league):
    """Looks up the list_id which corresponds to the given division and league.

    Args:
      division: Division of interest
      league: League of interest

    Returns:
      The list id corresponding to that league and division, or '' if no such
      list exists.
    """
    d = LIST_ID_MAP.get(league, {})
    if not d:
      return ''
    d = d.get(division, {})
    if not d:
      return ''
    return d.get(age_bracket, '')

  @staticmethod
  def _FindScoreIndicies(integer_entities, tweet_text):
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
        logging.info('Integers too far apart: %s', tweet_text)
        continue
      # The score can't be too high. Some AUDL / MLU games might go to 
      # high scores if there are multiple overtimes.
      if entA.num + entB.num > 100:
        logging.info('Numbers sum to too high of a number: %s', tweet_text)
        continue
      if tweet_text[entA.end_idx:entB.start_idx].find('-') != -1:
        return [i, i+1]
      logging.info('Could not find "-" in tweet text: %s', tweet_text)
    # TODO: need to do something more sophisticated for this days with multiple
    # games.
    return []

  @staticmethod
  def _PossiblyEnqueueCrawling():
    """Trigger a crawl if that hasn't been done in a while."""
    host = app_identity.app_identity.get_default_version_hostname()
    if not host or host.find('localhost') != -1:
      logging.info('Local dev/test environment detected - Not enqueuing crawl')
      return
    
    # Get the most recent tweet and compare it to UTC now
    now = datetime.utcnow()
    twts = tweets.Tweet.query().order(-tweets.Tweet.created_at).fetch(1)

    if len(twts) and now - twts[0].created_at < timedelta(
        hours=MAX_HOURS_CRAWL_LATENCY):
      logging.debug('Not triggering crawl: time of last crawled tweet %s',
          twts[0].created_at)
      return

    logging.info('Database stale - triggering crawl')
    taskqueue.add(url='/tasks/crawl_all_lists', method='GET',
        queue_name='list-statuses')

  @endpoints.method(GamesRequest, GamesResponse,
                    path='all_games', http_method='GET')
  def GetGames(self, request):
    """Exposes an API endpoint to retrieve the scores of multiple games.

    Can be reference on dev server by using the following URL:
    http://localhost:8080/_ah/api/scores/v1/game
    Args:
        request: An instance of GamesRequest parsed from the API request.
    Returns:
        An instance of GamesResponse with the set of known games matching
        the request parameters.
    """
    # If the lists haven't been crawled in a while, crawl them.
    self._PossiblyEnqueueCrawling()
    # TODO: if no division, league, or age_bracket specified, throw an error.
    twts = self._LookupMatchingTweets(request)
    logging.info('Found %d potentially matching tweets', len(twts))

    response = GamesResponse()

    response.games = []

    teams_accounted_for = set()

    for twt in twts:
      score_indicies = ScoresApi._FindScoreIndicies(
          twt.entities.integers, twt.text)

      if not score_indicies:
        logging.info('Ignoring tweet: %s', twt.text)
        continue
      else:
        logging.info('Found suitable score in tweet: %s', twt.text)

      if twt.author_id_64 in teams_accounted_for:
        logging.info('Discarding tweet as part of another game: %s', twt.text)
        continue

      game = Game()
      game.teams = [Team(), Team()]
      account = TwitterAccount()
      account.screen_name = twt.author_screen_name
      account.id_str = twt.author_id
      teams_accounted_for.add(twt.author_id_64)

      # TODO: lookup user name and profile image URL using memcache
      account_query = tweets.User.query().order(tweets.User.screen_name)
      account_query = account_query.filter(tweets.User.id_str == twt.author_id)
      user = account_query.fetch(1)
      if user:
        user = user[0]
        account.user_defined_name = user.name
        account.profile_image_url_https = user.profile_image_url_https
      else:
        logging.info('Could not look up user for id %s', twt.author_id)

      game.teams[0].twitter_account = account
      game.teams[1].score_reporter_id = 'unknown id'
      game.scores = [twt.entities.integers[score_indicies[0]].num,
          twt.entities.integers[score_indicies[1]].num]
      game.id_str = 'game_%s' % str(uuid.uuid4())
      game.name = ''
      game.tournament_id_str = 'tourney_%s' % str(uuid.uuid4())
      game.tournament_name = 'Unknown tournament'
      game.league = request.league
      game.division = request.division
      game.age_bracket = request.age_bracket
      game.game_status = GameStatus.UNKNOWN
      source = GameSource()
      source.type = GameSourceType.TWITTER
      localized_date = twt.created_at
      if request.local_time and request.local_time.utcoffset():
        localized_date = localized_date + request.local_time.utcoffset()
      source.update_time_utc_str = localized_date.strftime(
          tweets.DATE_PARSE_FMT_STR)
      source.twitter_account = TwitterAccount()
      source.twitter_account.screen_name = twt.author_screen_name
      source.twitter_account.id_str = twt.id_str
      source.tweet_text = twt.text 
      game.last_update_source = source

      response.games.append(game)

    return response

  @endpoints.method(GameInfoRequest, GameInfoResponse,
                    path='game', http_method='GET',
                    name='game.info')
  def GetGameInfo(self, request):
    """Exposes an API endpoint to query for scores for the current user.
    Args:
        request: An instance of ScoresListRequest parsed from the API
            request.
    Returns:
        An instance of ScoresListResponse containing the scores for the
        current user returned in the query. If the API request specifies an
        order of WHEN (the default), the results are ordered by time from
        most recent to least recent. If the API request specifies an order
        of TEXT, the results are ordered by the string value of the scores.
    """
    response = GameInfoResponse()
    #source = GameSource()
    #source.source_type = GameSourceType.SCORE_REPORTER
    #response.score_reporter_source = source

    return response

app = endpoints.api_server([ScoresApi], restricted=False)
