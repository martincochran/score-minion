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
import uuid

from google.appengine.ext import ndb
from google.appengine.ext.ndb import msgprop

import scores_messages
import tweets

DEFAULT_GAME_DB_NAME = 'game_db'
DEFAULT_TEAM_TABLE_NAME = 'team_db'
FULL_INFO_TABLE_NAME = 'full_team_info_db'
SR_TEAM_TABLE_NAME = 'team_db'

class GameModelError(Exception):
  pass


# On App Engine prod this will be set correctly, but in a unittest environment
# the version will not be set when this is executed.
APP_VERSION = os.environ.get('CURRENT_VERSION_ID', '-1')


UNKNOWN_TOURNAMENT_ID = "unknown_id"


# We want operations on an individual game to be consistent.
def game_key_full(game_id, game_table_name=DEFAULT_GAME_DB_NAME):
  return ndb.Key('Game', '%s_%s' % (DEFAULT_GAME_DB_NAME, game_id))


def game_key(proto_obj):
  """Build a key from a scores_messages.Game protobuf object."""
  # TODO: this probably needs to be the score-reporter game ID of
  # some sort (SR assigns unique game ids), otherwise there will be
  # no consistent way for the crawler to determine if a game is
  # already in the DB.
  return game_key_full(proto_obj.id_str)


# There are two tables for teams: Twitter accounts and Score Reporter ids.
# If both exist, then the two entries should be consistent.
def team_twitter_key(team_twitter_id, team_table_name=DEFAULT_TEAM_TABLE_NAME):
  return ndb.Key('Team', '%s_%s' % (team_table_name, team_twitter_id)) 


def team_score_reporter_key(team_sr_id, team_table_name=SR_TEAM_TABLE_NAME):
  return ndb.Key('Team', '%s_%s' % (team_table_name, team_sr_id)) 


def full_team_info_key(team_sr_id, team_table_name=FULL_INFO_TABLE_NAME):
  return ndb.Key('FullTeamInfo', '%s_%s' % (team_table_name, team_sr_id))


class TeamIdLookup(ndb.Model):
  """Model to store mapping from TeamIds to team tourney IDs."""

  # ID of team on score reporter
  score_reporter_id = ndb.StringProperty('id')

  # Tournament-specific tournament ID associated with this team.
  score_reporter_tourney_id = ndb.StringProperty('t_id', repeated=True)


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


class FullTeamInfo(ndb.Model):
  """Model version of the info available on score reporter for a team."""
  # Score reporter ID.
  id = ndb.StringProperty('sr_u')

  name = ndb.StringProperty('n')

  # TODO: do maps API lookup and change to geo pt.
  #city = ndb.StringProperty('c')

  age_bracket = msgprop.EnumProperty(scores_messages.AgeBracket, 'a')

  division = msgprop.EnumProperty(scores_messages.Division, 'd')

  # Twitter screen name
  screen_name = ndb.StringProperty('t')

  # Team website.
  website = ndb.StringProperty('u')

  # Facebook URL.
  facebook_url = ndb.StringProperty('f')

  @classmethod
  def FromTeamInfo(cls, team_info, division, age_bracket, key=None):
    """Creates a FullTeamInfo object from a sr_crawler.TeamInfo object."""
    return FullTeamInfo(
        id=team_info.id,
        name=team_info.name,
        # city=team_info.city,
        age_bracket=age_bracket,
        division=division,
        website=team_info.website,
        screen_name=team_info.twitter_screenname,
        facebook_url=team_info.facebook_url,
        key=key,
    )

class GameSource(ndb.Model):
  # Which type of game source is this?
  type = msgprop.EnumProperty(scores_messages.GameSourceType, 'st')

  update_date_time = ndb.DateTimeProperty('ut')

  # URL of game where update was crawled.
  score_reporter_url = ndb.StringProperty('url')

  # Twitter ID of account which contributed to this game.
  account_id = ndb.IntegerProperty('a_id')

  # ID of tweet adding the source
  tweet_id = ndb.IntegerProperty('t_id')

  # Text from the tweet.
  tweet_text = ndb.StringProperty('tt')

  @classmethod
  def FromProto(cls, proto_obj):
    """Create GameSource ndb object from the API Proto.

    The conversion is lossy since the API Proto does not have the tweet ID.
    """
    source = GameSource()
    source.type = proto_obj.type
    if proto_obj.update_time_utc_str:
      source.update_date_time = datetime.datetime.strptime(
          proto_obj.update_time_utc_str, tweets.DATE_PARSE_FMT_STR)
    else:
      source.update_date_time = datetime.datetime.now()
    if proto_obj.twitter_account:
      source.account_id = long(proto_obj.twitter_account.id_str)
      source.tweet_text = proto_obj.tweet_text
    if proto_obj.score_reporter_url:
      source.score_reporter_url = proto_obj.score_reporter_url
    if not (source.account_id or source.score_reporter_url):
      raise GameModelError('Converting GameSource from malformed proto')
    return source

  # TODO: also add FromScoreReporter once crawling / db is enabled there.
  @classmethod
  def FromTweet(cls, twt):
    return GameSource(type=scores_messages.GameSourceType.TWITTER,
                      update_date_time=twt.created_at,
                      tweet_text=twt.text,
                      tweet_id=twt.id_64,
                      account_id=twt.author_id_64)
  def ToProto(self):
    source = scores_messages.GameSource()
    source.type = self.type
    if self.update_date_time:
      source.update_time_utc_str = self.update_date_time.strftime(
          tweets.DATE_PARSE_FMT_STR)
    else:
      source.update_time_utc_str = datetime.datetime.now().strftime(
          tweets.DATE_PARSE_FMT_STR)
    if self.account_id:
      account = scores_messages.TwitterAccount()
      account.id_str = str(self.account_id)
      source.twitter_account = account
      source.tweet_text = self.tweet_text
    if self.score_reporter_url:
      source.score_reporter_url = self.score_reporter_url
    return source


class SubTournament(ndb.Model):
  division = msgprop.EnumProperty(scores_messages.Division, 'd')

  age_bracket = msgprop.EnumProperty(scores_messages.AgeBracket, 'a')


class Tournament(ndb.Model):
  """Information about the score reporter tournament."""
  id_str = ndb.StringProperty('id', required=True)

  # URL for landing page of tournament. The URLs for a given division and
  # age bracket can be computed from this.
  url = ndb.StringProperty('u', required=True)

  name = ndb.StringProperty('n')

  # The specific divisions and age brackets in the tournament.
  sub_tournaments = ndb.StructuredProperty(SubTournament, 's', repeated=True)

  # Day the tournament starts. This must be before any of the games are played.
  start_date = ndb.DateTimeProperty('sd')

  # First day after all games are done. This must be later than the ending
  # of the last game.
  end_date = ndb.DateTimeProperty('ed')

  # Location of tournament
  location = ndb.GeoPtProperty('l')

class Game(ndb.Model):
  """Information about a single game including all sources."""
  id_str = ndb.StringProperty('id', required=True)

  teams = ndb.StructuredProperty(Team, 't', repeated=True)
  scores = ndb.IntegerProperty('s', repeated=True)

  name = ndb.StringProperty('n')

  tournament_id = ndb.StringProperty('tid')

  # TODO: consider adding a separate ID for score reporter

  tournament_name = ndb.StringProperty('tn')

  game_status = msgprop.EnumProperty(scores_messages.GameStatus, 'gs')

  division = msgprop.EnumProperty(scores_messages.Division, 'd')

  league = msgprop.EnumProperty(scores_messages.League, 'l')

  age_bracket = msgprop.EnumProperty(scores_messages.AgeBracket, 'a')

  # There must be at least one source for each game.
  sources = ndb.StructuredProperty(GameSource, 'so', repeated=True)

  # Date & time the game was created in the DB, or the creation date of the
  # tweet it was initialized from if that was the creation method.
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
                # TODO: change this to key=?
                parent=game_key(proto_obj))

  @classmethod
  def FromTweet(cls, twt, teams, scores, division, age_bracket, league):
    """Builds a Game object from a tweet and the specified teams.

    Args:
      twt: The tweets.Tweet object
      teams: A list of exactly two Team objects derived from that Tweet.
      scores: A list of exactly two integer scores derived from that Tweet.
      division: The Division of the teams playing.
      age_bracket: The AgeBracket of the teams playing.
      league: The League of the teams playing.
    Returns:
      A Game object with the given properties.
    """
    game_id = 'game_%s' % str(uuid.uuid4())
    tournament_id = 'tourney_%s' % str(uuid.uuid4())
    return Game(id_str=game_id,
        teams=teams,
        scores=scores,
        name='',
        tournament_id=tournament_id,
        tournament_name='Unknown tournament',
        game_status=scores_messages.GameStatus.UNKNOWN,
        division=division,
        league=league,
        age_bracket=age_bracket,
        created_at=twt.created_at,
        last_modified_at=twt.created_at,
        sources=[GameSource.FromTweet(twt)],
        parent=game_key_full(game_id))

  @classmethod
  def FromGameInfo(cls, info):
    """Builds Game from GameInfo object crawled from Score Reporter."""
    # Build team objects
    teams = []
    # Parse scores
    scores = []
    name = info.bracket_title or info.pool_name
    status = scores_messages.GameStatus.UNKNOWN
    if info.status.lower() == 'final':
      status = scores_messages.GameStatus.FINAL
    return Game(id_str=info.id,
        name=name,
        teams=teams,
        scores=scores,
        # TODO: this means the tourney ID will be score-reporter
        # generated. This may or may not be a good thing.
        tournament_id=info.tourney_id,
        tournament_name=info.tourney_name,
        division=info.division,
        age_bracket=info.age_bracket,
        league=scores_messages.League.USAU,
        created_at=info.created_at,
        last_modified_at=datetime.datetime.utcnow(),
        # TODO: create proper source
        sources=[],
        # TODO: need to use another ID in order for game lookups to be consistent
        parent=game_key_full(info.id))


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
      game.last_update_source = self.sources[0].ToProto()
    return game
