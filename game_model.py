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
import os
import uuid

from google.appengine.ext import ndb
from google.appengine.ext.ndb import msgprop

import scores_messages
import tweets

DEFAULT_GAME_DB_NAME = 'game_db'
DEFAULT_TOURNEY_DB_NAME = 'tourney_db'
DEFAULT_TEAM_TABLE_NAME = 'team_db'
FULL_INFO_TABLE_NAME = 'full_team_info_db'
SR_TEAM_TABLE_NAME = 'team_db'


# Example date: '8/30/2015 11:30 AM'
BRACKET_DATE_FMT_STR = '%m/%d/%Y %I:%M %p'

# Example date: Sat '8/29 2015 9:30 AM'
POOL_DATE_FMT_STR = '%a %m/%d %Y %I:%M %p'


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
  return game_key_full(proto_obj.id_str)


# We want operations on an individual tournaments to be consistent.
def tourney_key_full(tourney_id):
  return ndb.Key('Tournament', '%s_%s' % (DEFAULT_TOURNEY_DB_NAME, tourney_id))


def tourney_key(proto_obj):
  """Build a key from a scores_messages.Tournament protobuf object."""
  return tourney_key_full(proto_obj.id_str)


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
  """Information to identify a team in the games database.

  Only of the of fields is required. If both are specified, the Twitter
  ID is used.
  
  """
  # ID of associated account on Twitter
  twitter_id = ndb.IntegerProperty('t_id')

  # ID of team on score reporter
  # TODO(NEXT): UCSB's B team lists the A-team's twitter account. Need to
  # ensure there is only one team.
  # See also Arizona State-C (http://play.usaultimate.org/teams/events/Eventteam/?TeamId=OI%2fLAL7UzQ1fmx1Zfe2sp%2btWu%2b77BQH91GrFaX2EK1c%3d)
  # Bad entry: WCN5wzaUHStOAq5MsopkH6azfgxOtBc9osLJJzbr2%252FE%253D
  # Bad entry: WCN5wzaUHStOAq5MsopkH6azfgxOtBc9osLJJzbr2%252fE%253d
  # Bad entry: iRedIuNSEU%252bVbvgYot3d3pXMgds7j2m4fYF7OBRwdnk%253d (men's team twitter account vs. women's team SR ID)
  score_reporter_id = ndb.StringProperty('sr_u')

  @classmethod
  def FromProto(cls, proto_obj):
    """Creates a Team object from a scores_messages.Team object."""
    key=None
    if proto_obj.twitter_account:
      twitter_id = long(proto_obj.twitter_account.id_str)
      key = team_twitter_key(twitter_id)
    else:
      twitter_id = 0
    if proto_obj.score_reporter_account:
      score_reporter_id = proto_obj.score_reporter_account.id
      key = team_score_reporter_key(score_reporter_id)
    else:
      score_reporter_id = ''
    return Team(twitter_id=twitter_id, score_reporter_id=score_reporter_id,
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
    if self.score_reporter_id:
      account = scores_messages.ScoreReporterAccount()
      account.id = self.score_reporter_id
      team.score_reporter_account = account
    return team


class FullTeamInfo(ndb.Model):
  """Model version of the info available on score reporter for a team."""
  # Score reporter ID.
  id = ndb.StringProperty('sr_u')

  name = ndb.StringProperty('n')

  # TODO(P2): do maps API lookup and change to geo pt.
  #city = ndb.StringProperty('c')

  age_bracket = msgprop.EnumProperty(scores_messages.AgeBracket, 'a')

  division = msgprop.EnumProperty(scores_messages.Division, 'd')

  # Twitter screen name
  screen_name = ndb.StringProperty('t')

  # Team website.
  website = ndb.StringProperty('u')

  # Facebook URL.
  facebook_url = ndb.StringProperty('f')

  # Link to team profile image
  image_link = ndb.StringProperty('i')

  coach = ndb.StringProperty('co')

  asst_coach = ndb.StringProperty('aco')

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
        image_link=team_info.image_link,
        coach=team_info.coach,
        asst_coach=team_info.asst_coach,
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

  # The score this source represents.
  home_score = ndb.IntegerProperty('hs')
  away_score = ndb.IntegerProperty('as')

  @classmethod
  def FromProto(cls, proto_obj):
    """Create GameSource ndb object from the API Proto.

    The conversion is lossy since the API Proto does not have the tweet ID.
    """
    source = GameSource()
    source.type = proto_obj.type
    if proto_obj.update_time_utc_str:
      source.update_date_time = datetime.strptime(
          proto_obj.update_time_utc_str, tweets.DATE_PARSE_FMT_STR)
    else:
      source.update_date_time = datetime.now()
    if proto_obj.twitter_account:
      source.account_id = long(proto_obj.twitter_account.id_str)
      source.tweet_text = proto_obj.tweet_text
    if proto_obj.score_reporter_url:
      source.score_reporter_url = proto_obj.score_reporter_url
    if not (source.account_id or source.score_reporter_url):
      raise GameModelError('Converting GameSource from malformed proto')
    return source

  @classmethod
  def FromTweet(cls, twt, scores):
    return GameSource(type=scores_messages.GameSourceType.TWITTER,
                      update_date_time=twt.created_at,
                      tweet_text=twt.text,
                      home_score=scores[0],
                      away_score=scores[1],
                      tweet_id=twt.id_64,
                      account_id=twt.author_id_64)
  def ToProto(self):
    source = scores_messages.GameSource()
    source.type = self.type
    if self.update_date_time:
      source.update_time_utc_str = self.update_date_time.strftime(
          tweets.DATE_PARSE_FMT_STR)
    else:
      source.update_time_utc_str = datetime.now().strftime(
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

  last_modified_at = ndb.DateTimeProperty('lu')

  image_url_https = ndb.StringProperty('iu')
  
  league = msgprop.EnumProperty(scores_messages.League, 'le')

  def ToProto(self):
    """Builds a Tournament protobuf object from this instance."""
    tourney = scores_messages.Tournament()
    tourney.id_str = self.id_str
    tourney.url = self.url
    tourney.name = self.name
    tourney.image_url_https = self.image_url_https
    age_brackets = set()
    divisions = set()
    for st in self.sub_tournaments:
      age_brackets.add(st.age_bracket)
      divisions.add(st.division)
    tourney.divisions = sorted(list(divisions))
    tourney.age_brackets = sorted(list(age_brackets))
    tourney.start_date = self.start_date.strftime(
        tweets.DATE_PARSE_FMT_STR)
    tourney.end_date = self.end_date.strftime(
        tweets.DATE_PARSE_FMT_STR)
    tourney.last_modified_at = self.last_modified_at.strftime(
        tweets.DATE_PARSE_FMT_STR)
    return tourney


class Game(ndb.Model):
  """Information about a single game including all sources."""
  id_str = ndb.StringProperty('id', required=True)

  teams = ndb.StructuredProperty(Team, 't', repeated=True)
  scores = ndb.IntegerProperty('s', repeated=True)

  name = ndb.StringProperty('n')

  # Score reporter ID, if game exists in score reporter. Otherwise,
  # randomly chosen.
  tournament_id = ndb.StringProperty('tid')

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

  # If crawled from Score Reporter, the given start time.
  start_time = ndb.DateTimeProperty('st')

  @classmethod
  def FromProto(cls, proto_obj):
    """Builds a Game object from a protobuf object."""
    if not proto_obj.last_update_source:
      raise GameModelError('No update source specified in Game creation.')
    # TODO(P2): refactor all constructors into one base function like in tweets.
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
                key=game_key(proto_obj))

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
        sources=[GameSource.FromTweet(twt, scores)],
        key=game_key_full(game_id))

  @classmethod
  def FromGameInfo(cls, info, team_tourney_map):
    """Builds Game from GameInfo object crawled from Score Reporter.

    Args:
      info: score_reporter_crawler.GameInfo object
      team_tourney_map: Map from tournament-specific team links to
        stable IDs. info.home_team_link and info.away_team_link must
        be present in the map.
    """
    teams = [
        Team(score_reporter_id=team_tourney_map.get(info.home_team_link, '')),
        Team(score_reporter_id=team_tourney_map.get(info.away_team_link, '')),
    ]

    start_time = ParseStartTime(info.date, info.time)

    scores = []
    try:
      scores = [int(info.home_team_score),
          int(info.away_team_score)]
    except ValueError as e:
      if info.home_team_score.strip().lower() == 'w':
        scores = [1, -1]
      elif info.away_team_score.strip().lower() == 'w':
        scores = [-1, 1]
      else:
        # Unknown scores
        scores = [-1, -1]
    source = GameSource(type=scores_messages.GameSourceType.SCORE_REPORTER,
        score_reporter_url=info.tourney_id,
        update_date_time=datetime.utcnow()) 
      
    name = info.bracket_title or info.pool_name
    status = scores_messages.GameStatus.UNKNOWN
    if info.status.lower() == 'final':
      status = scores_messages.GameStatus.FINAL
    return Game(id_str=info.id,
        name=name,
        teams=teams,
        scores=scores,
        tournament_id=info.tourney_name,
        tournament_name=info.tourney_name.replace('-', ' '),
        division=info.division,
        age_bracket=info.age_bracket,
        league=scores_messages.League.USAU,
        game_status=status,
        created_at=info.created_at,
        start_time=start_time,
        last_modified_at=datetime.utcnow(),
        sources=[source],
        key=game_key_full(info.id))


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

def ParseStartTime(game_date, game_time):
  """Best-effort parsing of game date and time.

  Score reporter date / time comes in two flavors:
    'Sat 8/29' and '9:30 AM' or '8/29/2015 9:30 AM' and ''.

  This function tries to parse both and returns anything
  successful. For the unknown year, it tries this year,
  next, and prior, and returns the one closest to now.
    

  Args:
    game_date: (string) parsed date from Score Reporter.
    game_time: (string) parsed time from Score Reporter.
  Returns:
    A datetime object If the strings can be parsed,
    otherwise None.
  """
  if not game_date:
    return None

  # TODO: Find timezone of tournament based on GeoPt coordinates once
  # the Maps API integration is in place. For now, we just pretend all
  # tweets are from the mountain timezone, which should be close enough
  # for most purposes.
  utc_offset = timedelta(hours=7)

  full_date_str = ''
  try:
    d = int(game_date[0])
    return datetime.strptime(game_date, BRACKET_DATE_FMT_STR) + utc_offset
  except ValueError:
    pass

  # This means we have to guess the year :(
  current_year = datetime.utcnow().year
  max_delta = timedelta(days=(365 * 10))
  # We need to apply the closest date to crawl time, so we have to fix
  # the 'now' in this test.
  now = datetime(2016, 1, 9, 9, 30)
  correct_date = now
  # TODO: pass in the date parsed from the tournament landing page
  # and avoid this guessing game.
  # TODO: needs to be UTC to match twitter scores. Ensure test uses
  # actual twitter date format string.
  for year in [current_year, current_year - 1, current_year + 1]:
    full_date_str = '%s %s %s' % (game_date, year, game_time)
    try: 
      dt = datetime.strptime(full_date_str, POOL_DATE_FMT_STR)
    except ValueError:
      # Fall through, we will return None if nothing works.
      continue
    if abs(now - dt) < max_delta:
      max_delta = abs(now - dt)
      correct_date = dt
  
  if correct_date != now:
    return correct_date + utc_offset
  return None

