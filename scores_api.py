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


import endpoints

from protorpc import remote

from scores_messages import Game
from scores_messages import GameInfoRequest
from scores_messages import GameInfoResponse
from scores_messages import GameSource
from scores_messages import GameSourceType
from scores_messages import GamesRequest
from scores_messages import GamesResponse
from scores_messages import Team
from scores_messages import TwitterAccount


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
  def add_move_to_board(board_state):
    """Adds a random 'O' to a tictactoe board.
    Args:
        board_state: String; contains only '-', 'X', and 'O' characters.
    Returns:
        A new board with one of the '-' characters converted into an 'O';
        this simulates an artificial intelligence making a move.
    """
    result = list(board_state)  # Need a mutable object

#    free_indices = [match.start()
#                    for match in re.finditer('-', board_state)]
#    random_index = random.choice(free_indices)
#    result[random_index] = 'O'

    return ''.join(result)

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
    response = GamesResponse()
    # Add a couple fake, static games for testing.
    game1 = Game()
    game1.teams = [Team(), Team()]
    game1.teams[0].score_reporter_id = 'id 1'
    game1.teams[1].score_reporter_id = 'id 2'
    game1.scores = [5, 7]
    game1.id_str = 'abcde123'
    game1.name = 'Test game 1'
    game1.tournament_id_str = 'tourney_1234'
    game1.tournament_name = 'Test tourney'

    response.games = [game1]
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
