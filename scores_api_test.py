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
import json
import logging
import mock
import os
import unittest
import webtest

import test_env_setup

from google.appengine.api import app_identity
from google.appengine.api import taskqueue
from google.appengine.ext import testbed

import endpoints
from endpoints import api_config

import game_model
import score_reporter_crawler
import score_reporter_handler
import tweets

# Mock out the endpoints method
def null_decorator(*args, **kwargs):
    def decorator(method):
        def wrapper(*args, **kwargs):
            return method(*args, **kwargs)
        return wrapper
    return decorator

endpoints.method = null_decorator

# For some reason this is necessary before importing scores_api
# and using endpoints.
os.environ['CURRENT_VERSION_ID'] = '1.2'
import scores_api
import scores_messages
import web_test_base

class ScoresApiTest(web_test_base.WebTestBase):
  def setUp(self):
    super(ScoresApiTest, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_taskqueue_stub()
    self.testbed.init_datastore_v3_stub()
    self.api = scores_api.ScoresApi()

    self.testapp = webtest.TestApp(scores_api.app)

  def testSanityGetGames(self):
    """Ensure no exceptions are thrown on simple requests to GetGames."""
    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

  def testSanityGetTournaments(self):
    """Ensure no exceptions are thrown on simple requests to GetTournaments."""
    self.assertEqual(scores_messages.TournamentsResponse(),
        self.api.GetTournaments(scores_messages.TournamentsRequest()))

  def testSanityGetGameInfo(self):
    """Ensure no exceptions are thrown on simple requests to GetGameInfo."""
    self.assertEqual(scores_messages.GameInfoResponse(),
        self.api.GetGameInfo(scores_messages.GameInfoRequest()))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_gameTweet(self, mock_add_queue, mock_app_identity):
    """Verify the API handles the case where a game is returned."""
    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    user = self.CreateUser(2, 'bob')
    user.put()

    twt = web_test_base.WebTestBase.CreateTweet(
        1, ('bob', 2), created_at=datetime.utcnow())
    teams = [game_model.Team(twitter_id=2), game_model.Team(twitter_id=3)]
    game = game_model.Game.FromTweet(twt, teams, [0, 0],
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION, scores_messages.League.USAU)
    game.put()
    self.assertGameDbSize(1)

    # Request with all operators
    request = scores_messages.GamesRequest()
    request.league = scores_messages.League.USAU
    request.division = scores_messages.Division.OPEN
    request.age_bracket = scores_messages.AgeBracket.NO_RESTRICTION

    response = self.api.GetGames(request)
    self.assertEquals(1, len(response.games))
    self.assertEquals(2, len(response.games[0].teams))
    self.assertEquals('bob',
        response.games[0].teams[0].twitter_account.screen_name)
    self.assertEquals('bob',
        response.games[0].last_update_source.twitter_account.screen_name)

    # Request with no operators
    request = scores_messages.GamesRequest()
    response = self.api.GetGames(request)
    self.assertEquals(1, len(response.games))

    # Request with wrong division operator
    request = scores_messages.GamesRequest()
    request.division = scores_messages.Division.MIXED
    response = self.api.GetGames(request)
    self.assertEquals(0, len(response.games))

    # Request with wrong league operator
    request = scores_messages.GamesRequest()
    request.league = scores_messages.League.AUDL
    response = self.api.GetGames(request)
    self.assertEquals(0, len(response.games))

    # Request with wrong age bracket operator
    request = scores_messages.GamesRequest()
    request.age_bracket = scores_messages.AgeBracket.MASTERS
    response = self.api.GetGames(request)
    self.assertEquals(0, len(response.games))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_scoreReporterGame(self, mock_add_queue, mock_app_identity):
    """Verify the API handles the case where a SR game is returned."""
    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    user = self.CreateUser(2, 'bob')
    user.put()

    teams = [game_model.Team(score_reporter_id='a'),
        game_model.Team(score_reporter_id='b')]
    info = score_reporter_crawler.GameInfo(
        'a', 'b', 'name', scores_messages.Division.WOMENS,
        scores_messages.AgeBracket.NO_RESTRICTION)
    info.home_team_link = 'c'
    info.away_team_link = 'd'
    team_tourney_map = {
        'c': 'e',
        'd': 'f',
    }
    game = game_model.Game.FromGameInfo(info, team_tourney_map)
    game.put()
    self.assertGameDbSize(1)

    team_info = game_model.FullTeamInfo(
        key=game_model.full_team_info_key('e'),
        id='e',
        name='name',
        age_bracket=scores_messages.AgeBracket.NO_RESTRICTION,
        division=scores_messages.Division.WOMENS,
        website='website',
        screen_name='twitter_screenname',
        facebook_url='facebook_url',
        image_link='image_link',
        coach='coach',
        asst_coach='asst_coach')
    team_info.put()

    # Request with all operators
    request = scores_messages.GamesRequest()
    request.league = scores_messages.League.USAU
    request.division = scores_messages.Division.WOMENS
    request.age_bracket = scores_messages.AgeBracket.NO_RESTRICTION

    response = self.api.GetGames(request)
    self.assertEquals(1, len(response.games))
    self.assertEquals(2, len(response.games[0].teams))

    account = scores_messages.ScoreReporterAccount(
        id='e',
        name='name',
        team_website='website',
        facebook_url='facebook_url',
        screen_name='twitter_screenname',
        profile_image_url_https='%s%s' % (scores_api.USAU_PREFIX, 'image_link'),
        coach='coach',
        asst_coach='asst_coach')
    self.assertEquals(account,
        response.games[0].teams[0].score_reporter_account)
    account = scores_messages.ScoreReporterAccount(id='f')
    self.assertEquals(account,
        response.games[0].teams[1].score_reporter_account)

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_gameTweetNoKnownTeams(self, mock_add_queue,
      mock_app_identity):
    """A game is returned with no known teams."""
    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    twt = web_test_base.WebTestBase.CreateTweet(
        1, ('bob', 2), created_at=datetime.utcnow())
    teams = [game_model.Team(twitter_id=2), game_model.Team(
      score_reporter_id='unknown')]
    game = game_model.Game.FromTweet(twt, teams, [0, 0],
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION, scores_messages.League.USAU)
    game.put()
    self.assertGameDbSize(1)

    request = scores_messages.GamesRequest()
    request.league = scores_messages.League.USAU
    request.division = scores_messages.Division.OPEN
    request.age_bracket = scores_messages.AgeBracket.NO_RESTRICTION

    response = self.api.GetGames(request)
    self.assertEquals(1, len(response.games))
    self.assertEquals(2, len(response.games[0].teams))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_noTriggerCrawl(self, mock_add_queue, mock_app_identity):
    """Ensure crawl is not triggered if the datebase is up-to-date."""
    # Add a tweet to the database that was recently crawled.
    twt = self.CreateTweet('2', ['bob', '5'])
    twt.put()

    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_triggerCrawl(self, mock_add_queue, mock_app_identity):
    """Ensure crawl is triggered if the database is stale."""
    # Add a tweet to the database that was crawled yesterday.
    yesterday_date = datetime.now() - timedelta(days=1)

    # Subtract the delta that's used in the API logic.
    yesterday_date = yesterday_date - timedelta(
        hours=scores_api.MAX_HOURS_CRAWL_LATENCY)
    twt = self.CreateTweet('2', ['bob', '5'], created_at=yesterday_date)
    twt.put()

    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGames_noTweetstriggerCrawl(self, mock_add_queue,
      mock_app_identity):
    """Ensure crawl is triggered when there are no tweets."""
    mock_app_identity.get_default_version_hostname = mock.MagicMock()
    mock_app_identity.get_default_version_hostname.return_value = 'production host'

    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGameInfo(self, mock_add_queue, mock_app_identity):
    """Test basic functionality of GetGameInfo."""
    twt = web_test_base.WebTestBase.CreateTweet(
        1, ('bob', 2), created_at=datetime.utcnow())
    game = game_model.Game.FromTweet(twt, [], [0, 0], scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION, scores_messages.League.USAU)
    game.put()
    self.assertGameDbSize(1)

    game_id = game.id_str

    # First query with the wrong game ID.
    request = scores_messages.GameInfoRequest()
    request.game_id_str = game_id + 'extra_text'
    response = self.api.GetGameInfo(request)
    self.assertEquals(0, len(response.twitter_sources))
    self.assertEquals(None, response.score_reporter_source)
    self.assertEquals(None, response.game)

    request = scores_messages.GameInfoRequest()
    request.game_id_str = game_id
    response = self.api.GetGameInfo(request)
    self.assertEquals(1, len(response.twitter_sources))
    self.assertEquals(None, response.score_reporter_source)
    self.assertEquals(game_id, response.game.id_str)

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetGameInfo_scoreReporterSource(self, mock_add_queue,
      mock_app_identity):
    """Test functionality of GetGameInfo using a SR source."""
    game_info = score_reporter_crawler.GameInfo(
        'id', 'tourney_id', 'name', scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION)
    team_tourney_map = {
    }
    game = game_model.Game.FromGameInfo(game_info, team_tourney_map)
    game.put()
    self.assertGameDbSize(1)

    game_id = game.id_str

    request = scores_messages.GameInfoRequest()
    request.game_id_str = game_id
    response = self.api.GetGameInfo(request)
    self.assertEquals(0, len(response.twitter_sources))
    self.assertEquals('tourney_id',
        response.score_reporter_source.score_reporter_url)
    self.assertEquals(game_id, response.game.id_str)

  @mock.patch.object(app_identity, 'app_identity')
  @mock.patch.object(taskqueue, 'add')
  def testGetTournaments(self, mock_add_queue, mock_app_identity):
    """Test non-trivial functionality of GetTournaments."""
    # Add 3 tournaments.
    # 1 with no games.
    name = 'no-games-tourney'
    key = game_model.tourney_key_full(name)
    tourney = game_model.Tournament(
        last_modified_at=datetime.utcnow(),
        key=key,
        start_date=datetime(2016, 5, 31, 0, 0),
        end_date=datetime(2016, 5, 31, 0, 0),
        sub_tournaments=[game_model.SubTournament(
          division=scores_messages.Division.OPEN,
          age_bracket=scores_messages.AgeBracket.COLLEGE)
        ],
        url='%s%s' % (score_reporter_handler.USAU_URL_PREFIX, name),
        id_str=name, name=name)
    tourney.put()
    # 1 with all games that have not started.
    name = 'not-started-tourney'
    key = game_model.tourney_key_full(name)
    tourney = game_model.Tournament(
        last_modified_at=datetime.utcnow(),
        key=key,
        start_date=datetime(2016, 5, 31, 0, 0),
        end_date=datetime(2016, 5, 31, 0, 0),
        sub_tournaments=[game_model.SubTournament(
          division=scores_messages.Division.OPEN,
          age_bracket=scores_messages.AgeBracket.COLLEGE)
        ],
        url='%s%s' % (score_reporter_handler.USAU_URL_PREFIX, name),
        id_str=name, name=name)
    tourney.put()
    game_model.Game(scores=[0, 0], tournament_id=name, id_str='a',
        created_at=datetime.utcnow()).put()

    # 1 with in-progress games and one game that hasn't started.
    name = 'in-progress-tourney'
    key = game_model.tourney_key_full(name)
    tourney = game_model.Tournament(
        last_modified_at=datetime.utcnow(),
        key=key,
        start_date=datetime(2016, 5, 31, 0, 0),
        end_date=datetime(2016, 5, 31, 0, 0),
        sub_tournaments=[game_model.SubTournament(
          division=scores_messages.Division.OPEN,
          age_bracket=scores_messages.AgeBracket.COLLEGE)
        ],
        url='%s%s' % (score_reporter_handler.USAU_URL_PREFIX, name),
        id_str=name, name=name)
    tourney.put()
    game_model.Game(scores=[0, 0], tournament_id=name, id_str='b',
        created_at=datetime.utcnow()).put()
    game_model.Game(scores=[1, 2], tournament_id=name, id_str='c',
        created_at=datetime.utcnow()).put()

    request = scores_messages.TournamentsRequest()
    response = self.api.GetTournaments(request)
    self.assertEquals(1, len(response.tournaments))
    self.assertEquals(name, response.tournaments[0].name)
    self.assertEquals(1, len(response.tournaments[0].games))


if __name__ == '__main__':
  unittest.main()
