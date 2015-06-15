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
import os

from google.appengine.ext import ndb
from google.appengine.ext.ndb import msgprop

import scores_messages
import tweets

DEFAULT_GAME_DB_NAME = 'game_db'
DEFAULT_TEAM_TABLE_NAME = 'team_db'
SR_TEAM_TABLE_NAME = 'team_db'

class GameModelError(Exception):
  pass


# On App Engine prod this will be set correctly, but in a unittest environment
# the version will not be set when this is executed.
APP_VERSION = os.environ.get('CURRENT_VERSION_ID', '-1')


UNKNOWN_TOURNAMENT_ID = "unknown_id"


# We want operations on an individual user to be consistent.
def game_key_full(game_id, game_table_name=DEFAULT_GAME_DB_NAME):
  return ndb.Key('Game', '%s_%s' % (DEFAULT_GAME_DB_NAME, game_id))


def game_key(proto_obj):
  """Build a key from a scores_messages.Game protobuf object."""
  return game_key_full(proto_obj.id_str)


# There are two tables for teams: Twitter accounts and Score Reporter ids.
# If both exist, then the two entries should be consistent.
def team_twitter_key(team_twitter_id, team_table_name=DEFAULT_TEAM_TABLE_NAME):
  return ndb.Key('Team', '%s_%s' % (team_table_name, team_twitter_id)) 


def team_score_reporter_key(team_sr_id, team_table_name=SR_TEAM_TABLE_NAME):
  return ndb.Key('Team', '%s_%s' % (team_table_name, team_sr_id)) 


class Team(ndb.Model):
  """Information to identify a team in the games database."""
  # ID of associated account on Twitter
  twitter_id = ndb.IntegerProperty('t_id')

  # ID of team on score reporter
  score_reporter_id = ndb.StringProperty('sr_u')

  @classmethod
  def FromProto(cls, proto_obj):
    """Creates a Team object from a scores_messages.Team object."""
    if proto_obj.twitter_account:
      twitter_id = long(proto_obj.twitter_account.id_str)
      key = team_twitter_key(twitter_id)
    else:
      twitter_id = 0
      key = team_score_reporter_key(proto_obj.score_reporter_id)
    return Team(twitter_id=twitter_id, score_reporter_id=proto_obj.score_reporter_id,
                parent=key)

  @classmethod
  def FromTwitterUser(cls, user):
    """Creates a Team object from a tweets.User object."""
    return Team(twitter_id=user.id_64)

  def ToProto(self):
    """Returns a scores_messages.Team object."""
    team = scores_messages.Team()
    if self.twitter_id:
      account = scores_messages.TwitterAccount()
      account.id_str = str(self.twitter_id)
      team.twitter_account = account
    team.score_reporter_id = self.score_reporter_id
    return team


class GameSource(ndb.Model):
  # Which type of game source is this?
  type = msgprop.EnumProperty(scores_messages.GameSourceType, 'st')

  update_date_time = ndb.DateTimeProperty('ut')

  # URL of game where update was crawled.
  score_reporter_url = ndb.StringProperty('url')

  # Twitter ID of account which contributed to this game.
  twitter_id = ndb.IntegerProperty('t_id')

  # Text from the tweet.
  tweet_text = ndb.StringProperty('tt')

  @classmethod
  def FromProto(cls, proto_obj):
    source = GameSource()
    source.type = proto_obj.type
    if proto_obj.update_time_utc_str:
      source.update_date_time = datetime.datetime.strptime(
          proto_obj.update_time_utc_str, tweets.DATE_PARSE_FMT_STR)
    else:
      source.update_date_time = datetime.datetime.now()
    if proto_obj.twitter_account:
      source.twitter_id = long(proto_obj.twitter_account.id_str)
      source.tweet_text = proto_obj.tweet_text
    if proto_obj.score_reporter_url:
      source.score_reporter_url = proto_obj.score_reporter_url
    if not (source.twitter_id or source.score_reporter_url):
      raise GameModelError('Converting GameSource from malformed proto')
    return source

  # TODO: also add FromScoreReporter once crawling / db is enabled there.
  @classmethod
  def FromTweet(cls, twt):
    return GameSource(type=scores_messages.GameSourceType.TWITTER,
                      update_date_time=twt.created_at,
                      tweet_text=twt.text,
                      twitter_id=twt.author_id_64)
  def ToProto(self):
    source = scores_messages.GameSource()
    source.type = self.type
    if self.update_date_time:
      source.update_time_utc_str = self.update_date_time.strftime(
          tweets.DATE_PARSE_FMT_STR)
    else:
      source.update_time_utc_str = datetime.datetime.now().strftime(
          tweets.DATE_PARSE_FMT_STR)
    if self.twitter_id:
      account = scores_messages.TwitterAccount()
      account.id_str = str(self.twitter_id)
      source.twitter_account = account
      source.tweet_text = self.tweet_text
    if self.score_reporter_url:
      source.score_reporter_url = self.score_reporter_url
    return source

# TODO: add a tournament class that can be used to look up tournaments when
# building the database from score reporter.


class Game(ndb.Model):
  """Information about a single game including all sources."""
  id_str = ndb.StringProperty('id', required=True)

  teams = ndb.StructuredProperty(Team, 't', repeated=True)
  scores = ndb.IntegerProperty('s', repeated=True)

  name = ndb.StringProperty('n')

  tournament_id = ndb.StringProperty('tid')

  tournament_name = ndb.StringProperty('tn')

  game_status = msgprop.EnumProperty(scores_messages.GameStatus, 'gs')

  division = msgprop.EnumProperty(scores_messages.Division, 'd')

  league = msgprop.EnumProperty(scores_messages.League, 'l')

  age_bracket = msgprop.EnumProperty(scores_messages.AgeBracket, 'a')

  # There must be at least one source for each game.
  sources = ndb.StructuredProperty(GameSource, 'so', repeated=True)

  # Date & time the game was created in the DB.
  created_at = ndb.DateTimeProperty('cd', required=True)

  # Last time the Game was updated.
  last_modified_at = ndb.DateTimeProperty('lm')


  @classmethod
  def FromProto(cls, proto_obj):
    """Builds a Game object from a protobuf object."""
    if not proto_obj.last_update_source:
      raise GameModelError('No update source specified in Game creation.')
    return Game(id_str=proto_obj.id_str,
                teams=[Team.FromProto(tm) for tm in proto_obj.teams],
                scores=proto_obj.scores,
                name=proto_obj.name,
                tournament_id=proto_obj.tournament_id_str,
                tournament_name=proto_obj.tournament_name,
                game_status=proto_obj.game_status,
                division=proto_obj.division,
                league=proto_obj.league,
                age_bracket=proto_obj.age_bracket,
                sources=[GameSource.FromProto(proto_obj.last_update_source)],
                parent=game_key(proto_obj))

  def ToProto(self):
    """Builds a Game protobuf object from this instance."""
    game = scores_messages.Game()
    game.id_str = self.id_str
    game.teams = [team.ToProto() for team in self.teams]
    game.scores = self.scores
    game.name = self.name
    game.tournament_id_str = self.tournament_id
    game.tournament_name = self.tournament_name
    game.game_status = self.game_status
    game.division = self.division
    game.league = self.league
    game.age_bracket = self.age_bracket
    if self.sources:
      game.last_update_source = self.sources[-1].ToProto()
    return game
