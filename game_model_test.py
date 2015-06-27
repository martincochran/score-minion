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

  def testTeamSerialization(self):
    """Verify serialization between Team protobuf and ndb classes."""
    # Serialize with full account
    team = scores_messages.Team()
    account = scores_messages.TwitterAccount()
    account.id_str = '1234'
    team.twitter_account = account
    team.score_reporter_id = 'a.b.c'
    self.assertEquals(team, game_model.Team.FromProto(team).ToProto())

    # Twitter account only
    team = scores_messages.Team()
    account = scores_messages.TwitterAccount()
    account.id_str = '1234'
    team.twitter_account = account
    self.assertEquals(team, game_model.Team.FromProto(team).ToProto())

    # SR sccount only
    team = scores_messages.Team()
    team.score_reporter_id = 'a.b.c'
    self.assertEquals(team, game_model.Team.FromProto(team).ToProto())

  def testTeamFromUser(self):
    """Test Team creation from a tweets.User class."""
    user = tweets.User.fromJson(
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
        1, ('bob', 2), created_at=datetime.datetime.now())
    source = game_model.GameSource.FromTweet(twt)

    self.assertEquals(scores_messages.GameSourceType.TWITTER, source.type)
    self.assertEquals(None, source.score_reporter_url)
    self.assertEquals(twt.created_at, source.update_date_time)
    self.assertEquals(2, source.twitter_id)


if __name__ == '__main__':
  unittest.main()
