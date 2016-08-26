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
from scores_messages import TournamentsRequest
from scores_messages import TournamentsResponse
from scores_messages import GamesResponse
from scores_messages import TwitterAccount

import game_model
import tweets

MAX_HOURS_CRAWL_LATENCY = 1

# Client ID for testing
WEB_CLIENT_ID = '245407672402-oisb05fsubs9l96jfdfhn4tnmju4efqe.apps.googleusercontent.com'


USAU_PREFIX = 'https://play.usaultimate.org'
# TODO(P2): add Android client ID


@endpoints.api(name='scores', version='v1',
               description='Score Minion API')
               #allowed_client_ids=[WEB_CLIENT_ID, endpoints.API_EXPLORER_CLIENT_ID])
               #auth_level=AUTH_LEVEL.OPTIONAL)
class ScoresApi(remote.Service):
  """Class which defines Score Minion API v1."""

  @endpoints.method(TournamentsRequest, TournamentsResponse,
                    path='tournaments', http_method='GET')
  def GetTournaments(self, request):
    """Exposes an API endpoint to retrieve the latest tournaments.

    Can be referenced on dev server by using the following URL:
    http://localhost:8080/_ah/api/scores/v1/tournaments

    Args:
        request: An instance of TournamentsRequest parsed from the API request.
    Returns:
        An instance of TournamentsResponse with the set of known games matching
        the request parameters.
    """
    # If the lists haven't been crawled in a while, crawl them.
    response = TournamentsResponse()
    response.tournaments = []
    league = League.USAU
    for tourney in self._LookupMatchingTourneys(request):
      proto_tourney = tourney.ToProto()
      gr = GamesRequest(
          tournament_id=proto_tourney.id_str,
          count=200)
      for game in self._LookupMatchingGames(gr):
        proto_game = game.ToProto()
        # Don't worry about games that haven't started yet.
        if proto_game.scores[0] <= 0 and proto_game.scores[1] <= 0:
          continue
        proto_tourney.games.append(proto_game)
        league = proto_game.league

        # Populate the team info in the response.
        # TODO: investigate (likely high) impact on latency
        for team in proto_game.teams:
          self._AddAccountInfo(team.twitter_account,
              team.score_reporter_account)

        source = proto_game.last_update_source
        if source:
          self._AddAccountInfo(source.twitter_account, None)

      proto_tourney.league = league
      # Only append the tourney if there are games.
      if proto_tourney.games:
        response.tournaments.append(proto_tourney)
    return response

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
      proto_game = game.ToProto()
      response.games.append(proto_game)

      # Populate the team info in the response.
      for team in proto_game.teams:
        self._AddAccountInfo(team.twitter_account,
            team.score_reporter_account)

      source = proto_game.last_update_source
      if source:
        self._AddAccountInfo(source.twitter_account, None)

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
      # TODO(P2): throw error?
      return response
    games_query = game_model.Game.query(
        game_model.Game.id_str == request.game_id_str).order(
        -game_model.Game.last_modified_at)

    games = games_query.fetch(1)
    if not games:
      return response
    logging.debug('game returned: %s', games[0])
    response.game = games[0].ToProto()

    # Add team info to response
    for team in response.game.teams:
      self._AddAccountInfo(team.twitter_account, team.score_reporter_account)

    num_sources = request.max_num_sources
    if not num_sources:
      num_sources = 50

    num_added_sources = 0
    for source in games[0].sources:
      if source.type == GameSourceType.TWITTER:
        response.twitter_sources.append(source.ToProto())
        self._AddTwitterAccountInfo(
            response.twitter_sources[-1].twitter_account)
      else:
        response.score_reporter_source = source.ToProto()
      num_added_sources += 1
      if num_added_sources >= num_sources:
        break

    return response

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
    # TODO(P2): support other filters (by team id, eg)
    games_query = game_model.Game.query()
    if request.division:
      games_query = games_query.filter(game_model.Game.division == request.division)
    if request.age_bracket:
      games_query = games_query.filter(game_model.Game.age_bracket == request.age_bracket)
    if request.league:
      games_query = games_query.filter(game_model.Game.league == request.league)
    if request.tournament_id:
      games_query = games_query.filter(
          game_model.Game.tournament_id == request.tournament_id)

    games_query = games_query.order(-game_model.Game.last_modified_at)

    count = request.count
    if not count:
      count = num
    return games_query.fetch(count)

  @staticmethod
  def _LookupMatchingTourneys(request, num=25):
    """Returns a set of tournaments from the DB matching the request criteria.

    Args:
      request: TournamentsRequest object specifying what tournaments to look up
      num: Number of tournaments to retrieve from the DB

    Returns:
      The list of game_model.Tournament objects that match the criteria.
    """
    query = game_model.Tournament.query(game_model.Tournament.has_started == True)
    query = query.order(-game_model.Tournament.start_date)

    count = request.count
    if not count:
      count = num
    return query.fetch(count)

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

  def _AddAccountInfo(self, twitter_account, score_reporter_account):
    """Populate account fields with full account info.

    Args:
      twitter_account: scores_messages.TwitterAccount object.
      score_reporter_account: scores_messages.ScoreReporterAccount object.
    """
    if twitter_account:
      self._AddTwitterAccountInfo(twitter_account)
    if score_reporter_account:
      self._AddScoreReporterAccountInfo(score_reporter_account)

  @staticmethod
  def _AddTwitterAccountInfo(twitter_account):
    """Populate TwitterAccount with additional data from the datastore.

    Args:
      twitter_account: scores_messages.TwitterAccount object
    """
    user_id = twitter_account.id_str
    account_query = tweets.User.query().order(tweets.User.screen_name)
    account_query = account_query.filter(tweets.User.id_str == user_id)
    user = account_query.fetch(1)
    if not user:
      return
    twitter_account.screen_name = user[0].screen_name
    twitter_account.user_defined_name = user[0].name
    twitter_account.profile_image_url_https = user[0].profile_image_url_https

  @staticmethod
  def _AddScoreReporterAccountInfo(score_reporter_account):
    """Populate ScoreReporterAccount with additional data from the datastore.

    Args:
      score_reporter_account: scores_messages.ScoreReporterAccount object
    """
    id = score_reporter_account.id
    if not id:
      return
    info = game_model.full_team_info_key(id).get()
    if not info:
      return
    score_reporter_account.name = info.name
    score_reporter_account.team_website = info.website
    score_reporter_account.facebook_url = info.facebook_url
    score_reporter_account.profile_image_url_https = '%s%s' % (
        USAU_PREFIX, info.image_link)
    score_reporter_account.coach = info.coach
    score_reporter_account.asst_coach = info.asst_coach
    score_reporter_account.screen_name = info.screen_name


app = endpoints.api_server([ScoresApi], restricted=False)
