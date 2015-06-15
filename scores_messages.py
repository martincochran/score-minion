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

from protorpc import messages


class Division(messages.Enum):
  WOMENS = 1
  MIXED = 2
  OPEN = 3


class AgeBracket(messages.Enum):
  MASTERS = 1
  GRAND_MASTERS = 2
  U_23 = 3
  U_19 = 4
  COLLEGE = 5
  NO_RESTRICTION = 6


class League(messages.Enum):
  USAU = 1
  AUDL = 2
  MLU = 3
  WFDF_CLUB = 4
  WFDF_WORLDS = 5


class GameStatus(messages.Enum):
  NOT_STARTED = 1
  FINAL = 2
  IN_PROGRESS = 3
  UNKNOWN = 4


class TwitterAccount(messages.Message):
  # Twitter screen name.
  screen_name = messages.StringField(1)

  # Twitter id.
  id_str = messages.StringField(2)

  # Twitter user-supplied name.
  user_defined_name = messages.StringField(3)

  # URL of profile pic.
  profile_image_url_https = messages.StringField(4)


class Team(messages.Message):
  """Message to identify a team. At least one field must be present."""
  # Twitter account info.  At least screen_name or id_str must be present to
  # uniquely identify the team if passing as a request parameter.
  twitter_account = messages.MessageField(TwitterAccount, 1)

  # URL of score reporter page for that team.
  score_reporter_id = messages.StringField(2)


class GameSourceType(messages.Enum):
  SCORE_REPORTER = 1
  TWITTER = 2


class GameSource(messages.Message):
  """Source of latest model update to game."""
  type = messages.EnumField(GameSourceType, 1)

  # UTC time of game update as a string output by strftime.
  update_time_utc_str = messages.StringField(2)

  # URL of score reporter update, if appropriate.
  score_reporter_url = messages.StringField(3)

  # Twitter account info if from a tweet update.
  twitter_account = messages.MessageField(TwitterAccount, 4)

  # Text from the tweet.
  tweet_text = messages.StringField(5)


class Game(messages.Message):
  """Information to represent a game."""
  # Teams involved in the game.
  teams = messages.MessageField(Team, 1, repeated=True)

  # Scores of those teams, respectively.
  scores = messages.IntegerField(2, repeated=True)

  # Unique, opaque ID to represent game.
  id_str = messages.StringField(3)

  # Name of game. eg, "B3" or "Finals".
  name = messages.StringField(4)

  # Tournament with which this game is associated.
  tournament_id_str = messages.StringField(5)

  # Human-readable name of tournament. eg, "Club Nationals".
  tournament_name = messages.StringField(6)

  # Status of game. eg, IN_PROGRESS or FINAL.
  game_status = messages.EnumField(GameStatus, 7)

  # Division of game, eg, MIXED or OPEN.
  division = messages.EnumField(Division, 8)

  # League of game. eg, AUDL or USAU.
  league = messages.EnumField(League, 9)

  # Age division of game.
  age_bracket = messages.EnumField(AgeBracket, 10)

  # Source of most recent game update.
  last_update_source = messages.MessageField(GameSource, 11)


class GamesRequest(messages.Message):
  """ProtoRPC representation of a request for games."""
  # Pagination token returned in a prior GamesResponse. To paginate through
  # a series of results, this should be passed in subsequent calls to
  # GetGames.
  pagination_token = messages.StringField(1)

  # Maximum game start time.
  max_game_time_start_utc_secs = messages.IntegerField(2)

  # Minimum game start time.
  min_game_time_start_utc_secs = messages.IntegerField(3)

  # Maximum number of games that should be returned. If not specified, the
  # server is responsible for picking a suitable number.
  count = messages.IntegerField(4)

  # Division restriction. If absent, all divisions will be returned.
  division = messages.EnumField(Division, 5)

  # Age bracket restriction. If absent, all age brackets will be returned.
  age_bracket = messages.EnumField(AgeBracket, 6)

  # Tournament id string, if results from only that tournament are desired.
  tournament_id = messages.StringField(7)

  # Team. If specified, return only games for this team.
  team_id = messages.MessageField(Team, 8)

  # League of game. eg, AUDL or USAU.
  league = messages.EnumField(League, 9)


class GamesResponse(messages.Message):
  """Response for GetGames."""

  pagination_token = messages.StringField(1)

  games = messages.MessageField(Game, 2, repeated=True)


class GameInfoRequest(messages.Message):
  """Request for detailed info about one game."""

  # String ID of game
  game_id_str = messages.StringField(1)

  # If supplied, return this many sources for games. If not supplied, the
  # server will choose a suitable number.
  max_num_sources = messages.IntegerField(2)


class GameInfoResponse(messages.Message):
  """Response with detailed info about a game."""
  twitter_sources = messages.MessageField(GameSource, 1, repeated=True)

  score_reporter_source = messages.MessageField(GameSource, 2)


class PlayersOnTeamRequest(messages.Message):
  """Request to retrieve the players on a team."""
  team_id = messages.MessageField(Team, 1)


class PlayersOnTeamResponse(messages.Message):
  """Response with the player info for each player on a team."""
  players = messages.MessageField(TwitterAccount, 1, repeated=True)