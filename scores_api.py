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

import game_model
import tweets

MAX_HOURS_CRAWL_LATENCY = 1

# Client ID for testing
WEB_CLIENT_ID = '245407672402-oisb05fsubs9l96jfdfhn4tnmju4efqe.apps.googleusercontent.com'

# TODO: add Android client ID


@endpoints.api(name='scores', version='v1',
               description='Score Minion API')
               #allowed_client_ids=[WEB_CLIENT_ID, endpoints.API_EXPLORER_CLIENT_ID])
               #auth_level=AUTH_LEVEL.OPTIONAL)
class ScoresApi(remote.Service):
  """Class which defines Score Minion API v1."""

  @staticmethod
  def _LookupMatchingGames(request, num=10):
    """Returns a set of games from the DB matching the request criteria.

    Args:
      request: GamesRequest object specifying what games to look up
      num: Number of games to retrieve from the DB

    Returns:
      The list of game_model.Game objects that match the criteria.
    """
    # Currently the only request filter is by division.
    # TODO: support other filters (by tournament, eg)
    games_query = game_model.Game.query()
    if request.division:
      games_query = games_query.filter(game_model.Game.division == request.division)
    if request.age_bracket:
      games_query = games_query.filter(game_model.Game.age_bracket == request.age_bracket)
    if request.league:
      games_query = games_query.filter(game_model.Game.league == request.league)
    games_query = games_query.order(-game_model.Game.last_modified_at)

    count = request.count
    if not count:
      count = num
    return games_query.fetch(count)

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
    http://localhost:8080/_ah/api/scores/v1/all_games

    Args:
        request: An instance of GamesRequest parsed from the API request.
    Returns:
        An instance of GamesResponse with the set of known games matching
        the request parameters.
    """
    # If the lists haven't been crawled in a while, crawl them.
    self._PossiblyEnqueueCrawling()
    response = GamesResponse()
    response.games = []
    for game in self._LookupMatchingGames(request):
      response.games.append(game.ToProto())
      logging.info('returning game: %s', game)
    return response

  @endpoints.method(GameInfoRequest, GameInfoResponse,
                    path='game', http_method='GET')
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
    if not request.game_id_str:
      # TODO: throw error?
      return response
    games_query = game_model.Game.query(
        game_model.Game.id_str == request.game_id_str).order(
        -game_model.Game.last_modified_at)

    games = games_query.fetch(1)
    if not games:
      return response
    logging.info('game returned: %s', games[0])

    num_sources = request.max_num_sources
    if not num_sources:
      num_sources = 50

    num_added_sources = 0
    for source in games[0].sources:
      if source.type == GameSourceType.TWITTER:
        response.twitter_sources.append(source.ToProto())
      else:
        response.score_reporter_source = source.ToProto()
      num_added_sources += 1
      if num_added_sources >= num_sources:
        break

    return response

app = endpoints.api_server([ScoresApi], restricted=False)
