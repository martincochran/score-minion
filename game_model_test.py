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

import datetime
import json
import unittest
import uuid

import test_env_setup

import game_model
import score_reporter_crawler
import scores_messages
import tweets
import web_test_base


class GameModelTest(unittest.TestCase):
  """Unit tests for the GameModel DB classes and utility functions."""

  def testSanityGamesMessages(self):
    """Ensure no basic syntax errors in the model definition."""
    game_model.Game()
    game_model.Team()
    game_model.GameSource()

  def testGameSerialization(self):
    """Verify serialization between Game protobuf and ndb classes."""
    game = scores_messages.Game()
    game.id_str = str(uuid.uuid4())
    game.division = scores_messages.Division.WOMENS
    game.league = scores_messages.League.WFDF_CLUB
    game.last_update_source = scores_messages.GameSource()
    game.last_update_source.update_time_utc_str = 'Wed Dec 10 21:00:24 2014'
    game.last_update_source.score_reporter_url = 'http://a.b.c/'
    game.last_update_source.type = scores_messages.GameSourceType.SCORE_REPORTER
    self.assertEquals(game, game_model.Game.FromProto(game).ToProto())

  def testGameSerialization_noDateSpecified(self):
    """If there is no date specified, creation should succeed."""
    game = scores_messages.Game()
    game.id_str = str(uuid.uuid4())
    game.last_update_source = scores_messages.GameSource()
    game.last_update_source.score_reporter_url = 'http://a.b.c/'

    # Protos aren't equal because the date will be filled in.
    self.assertNotEquals(game, game_model.Game.FromProto(game).ToProto())

  def testGameSerialization_malformedProto(self):
    """Ensure an error is thrown if there is a malformed input proto."""
    game = scores_messages.Game()
    game.id_str = str(uuid.uuid4())
    game.last_update_source = scores_messages.GameSource()

    try:
      self.assertEquals(game, game_model.Game.FromProto(game).ToProto())
    except game_model.GameModelError:
      # Expected
      pass

  def testGameSerialization_multipleSources(self):
    """Verify that multiple sources get condensed down to one in an API Game."""
    game = game_model.Game()
    game.id_str = str(uuid.uuid4())
    sources = [game_model.GameSource(), game_model.GameSource()]
    sources[0].score_reporter_url = 'http://a.b.c/'
    sources[1].score_reporter_url = 'http://a.b.c/'
    game.sources = sources
    converted_game = game_model.Game.FromProto(game.ToProto())
    self.assertNotEquals(game, converted_game)
    self.assertEquals(1, len(converted_game.sources))

  def testGameSerialization_fromGameInfo(self):
    game_info = score_reporter_crawler.GameInfo('id', 'tourney_url',
        'tourney_name',
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION)
    game_info.home_team_score = '5'
    game_info.away_team_score = '6'
    game_info.status = 'Final'
    game_info.home_team_link = 'a'
    game_info.away_team_link = 'b'
    url_map = {'a': '123', 'b': '456'}
    converted_game = game_model.Game.FromGameInfo(game_info, url_map)

    self.assertEqual(scores_messages.Division.OPEN,
        converted_game.division)
    self.assertEqual(scores_messages.AgeBracket.NO_RESTRICTION,
        converted_game.age_bracket)
    self.assertEqual('id', converted_game.id_str)
    self.assertEqual('tourney_url', converted_game.tournament_id)
    self.assertEqual('tourney_name', converted_game.tournament_name)
    self.assertEqual([5, 6], converted_game.scores)
    self.assertEqual(scores_messages.GameStatus.FINAL,
        converted_game.game_status)

    self.assertEqual(1, len(converted_game.sources))
    date = datetime.datetime.utcnow()
    source = game_model.GameSource(
        type=scores_messages.GameSourceType.SCORE_REPORTER,
        score_reporter_url='tourney_url',
        update_date_time=date)
    converted_game.sources[0].update_date_time=date
    self.assertEqual([source], converted_game.sources)

    self.assertEqual(2, len(converted_game.teams))
    self.assertEqual('123', converted_game.teams[0].score_reporter_id)
    self.assertEqual('456', converted_game.teams[1].score_reporter_id)

  def testGameSerialization_fromGameInfoNonNumberScores(self):
    game_info = score_reporter_crawler.GameInfo('id', 'tourney_id',
        'tourney_name',
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION)
    game_info.home_team_score = 'W'
    game_info.away_team_score = 'L'
    converted_game = game_model.Game.FromGameInfo(game_info, {})
    self.assertEqual([1, -1], converted_game.scores)

    game_info.home_team_score = 'l'
    game_info.away_team_score = 'w'
    converted_game = game_model.Game.FromGameInfo(game_info, {})
    self.assertEqual([-1, 1], converted_game.scores)

    game_info.home_team_score = 'nonsense'
    game_info.away_team_score = 'nonsense'
    converted_game = game_model.Game.FromGameInfo(game_info, {})
    self.assertEqual([-1, -1], converted_game.scores)

  def testTeamSerialization(self):
    """Verify serialization between Team protobuf and ndb classes."""
    # Serialize with full account
    team = scores_messages.Team()
    account = scores_messages.TwitterAccount()
    account.id_str = '1234'
    team.twitter_account = account
    account = scores_messages.ScoreReporterAccount()
    account.id = 'a.b.c'
    team.score_reporter_account = account
    self.assertEquals(team, game_model.Team.FromProto(team).ToProto())

    # Twitter account only
    team = scores_messages.Team()
    account = scores_messages.TwitterAccount()
    account.id_str = '1234'
    team.twitter_account = account
    self.assertEquals(team, game_model.Team.FromProto(team).ToProto())

    # SR sccount only
    team = scores_messages.Team()
    account = scores_messages.ScoreReporterAccount()
    account.id = 'a.b.c'
    team.score_reporter_account = account
    self.assertEquals(team, game_model.Team.FromProto(team).ToProto())

  def testTeamFromUser(self):
    """Test Team creation from a tweets.User class."""
    user = tweets.User.FromJson(
        json.loads(
          '{"id_str": "1234", "id": 1234, "screen_name": "bob"}'))
    team = game_model.Team.FromTwitterUser(user)

    self.assertEquals(1234L, team.twitter_id)

  def testGameSourceSerialization_twitterAccount(self):
    """Test serialization between Twitter GameSource protos and ndb classes."""
    # Twitter source
    source = scores_messages.GameSource()
    source.type = scores_messages.GameSourceType.TWITTER
    source.update_time_utc_str = 'Wed Dec 10 21:00:24 2014'
    account = scores_messages.TwitterAccount()
    account.id_str = '1234'
    source.twitter_account = account
    self.assertEquals(source, game_model.GameSource.FromProto(source).ToProto())

  def testGameSourceSerialization_scoreReporter(self):
    """Test serialization between SR GameSource protobuf and ndb classes."""
    source = scores_messages.GameSource()
    source.update_time_utc_str = 'Wed Dec 10 21:00:24 2014'
    source.score_reporter_url = 'http://a.b.c/'
    self.assertEquals(source, game_model.GameSource.FromProto(source).ToProto())

  def testGameSourceFromTweet(self):
    """Test GameSource creation from a tweets.Tweet class."""
    twt = web_test_base.WebTestBase.CreateTweet(
        1, ('bob', 2), created_at=datetime.datetime.utcnow())
    source = game_model.GameSource.FromTweet(twt, [1, 2])

    self.assertEquals(scores_messages.GameSourceType.TWITTER, source.type)
    self.assertEquals(None, source.score_reporter_url)
    self.assertEquals(twt.created_at, source.update_date_time)
    self.assertEquals(2, source.account_id)
    self.assertEquals(1, source.home_score)
    self.assertEquals(2, source.away_score)

  def testGameFromTweet(self):
    """Test creating a Game from a Tweet."""
    twt = web_test_base.WebTestBase.CreateTweet(
        1, ('bob', 2), created_at=datetime.datetime.utcnow())
    game = game_model.Game.FromTweet(twt, [], [0, 0], scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION, scores_messages.League.USAU)

    self.assertFalse(game == None)

  def testFullTeamInfoSerialization(self):
    """Verify serialization between TeamInfo and the ndb class."""
    team_info = score_reporter_crawler.TeamInfo()
    team_info.id = 'team id'
    team_info.name = 'name'
    team_info.website = 'a'
    team_info.twitter_screenname = 'b'
    team_info.facebook_url = 'c'
    team_info.image_link = 'd'
    team_info.coach = 'e'
    team_info.asst_coach = 'f'

    expected_team_info = game_model.FullTeamInfo(
        id=team_info.id,
        name=team_info.name,
        age_bracket=scores_messages.AgeBracket.NO_RESTRICTION,
        division=scores_messages.Division.WOMENS,
        website=team_info.website,
        screen_name=team_info.twitter_screenname,
        facebook_url=team_info.facebook_url,
        image_link=team_info.image_link,
        coach=team_info.coach,
        asst_coach=team_info.asst_coach)
    self.assertEqual(game_model.FullTeamInfo.FromTeamInfo(team_info,
      scores_messages.Division.WOMENS,
      scores_messages.AgeBracket.NO_RESTRICTION),
        expected_team_info)
    
    game = scores_messages.Game()
    game.id_str = str(uuid.uuid4())
    game.division = scores_messages.Division.WOMENS
    game.league = scores_messages.League.WFDF_CLUB
    game.last_update_source = scores_messages.GameSource()
    game.last_update_source.update_time_utc_str = 'Wed Dec 10 21:00:24 2014'
    game.last_update_source.score_reporter_url = 'http://a.b.c/'
    game.last_update_source.type = scores_messages.GameSourceType.SCORE_REPORTER
    self.assertEquals(game, game_model.Game.FromProto(game).ToProto())

  def testParseStartTime(self):
    now = datetime.datetime.utcnow()
    # Games are parsed assuming mountain timezone, so UTC time will
    # be seven hours in the future.
    self.assertEqual(datetime.datetime(2015, 8, 29, 16, 30),
        game_model.ParseStartTime('Sat 8/29', '9:30 AM'))
    self.assertEqual(datetime.datetime(2016, 2, 29, 16, 30),
        game_model.ParseStartTime('Mon 2/29', '9:30 AM'))
    self.assertEqual(datetime.datetime(2015, 8, 30, 18, 30),
        game_model.ParseStartTime('8/30/2015 11:30 AM', ''))
    self.assertEqual(None, game_model.ParseStartTime('bad date', ''))
    self.assertEqual(None, game_model.ParseStartTime('Sat 8/29', '-11'))


if __name__ == '__main__':
  unittest.main()
