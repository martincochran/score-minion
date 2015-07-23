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

from game_model import Game
from scores_messages import AgeBracket
from scores_messages import Division
from scores_messages import League


class ListIdBiMap:
  """Encapsulates mappings to and from list id and structured properties."""

  # List ID definitions corresponding to lists defined in the twitter account of
  # @martin_cochran.
  USAU_COLLEGE_OPEN_LIST_ID = '186814318'
  USAU_COLLEGE_WOMENS_LIST_ID = '186814882'
  USAU_CLUB_OPEN_LIST_ID = '186732484'
  USAU_CLUB_WOMENS_LIST_ID = '186732631'
  USAU_CLUB_MIXED_LIST_ID = '186815046'
  AUDL_LIST_ID = '186926608'
  MLU_LIST_ID = '186926651'

  ALL_LISTS = [
      USAU_COLLEGE_OPEN_LIST_ID,
      USAU_COLLEGE_WOMENS_LIST_ID,
      USAU_CLUB_OPEN_LIST_ID,
      USAU_CLUB_WOMENS_LIST_ID,
      USAU_CLUB_MIXED_LIST_ID,
      AUDL_LIST_ID,
      MLU_LIST_ID
  ]

  # Simple data structure to lookup lists if the league, division, and age
  # bracket were specified in the request.
  LIST_ID_MAP = {
      League.USAU: {
        Division.OPEN: {
          AgeBracket.COLLEGE: USAU_COLLEGE_OPEN_LIST_ID,
          AgeBracket.NO_RESTRICTION: USAU_CLUB_OPEN_LIST_ID,
        },
        Division.WOMENS: {
          AgeBracket.COLLEGE: USAU_COLLEGE_WOMENS_LIST_ID,
          AgeBracket.NO_RESTRICTION: USAU_CLUB_WOMENS_LIST_ID,
        },
        Division.MIXED: {
          AgeBracket.NO_RESTRICTION: USAU_CLUB_MIXED_LIST_ID,
        },
      },
      League.AUDL: {
        Division.OPEN: {
          AgeBracket.NO_RESTRICTION: AUDL_LIST_ID,
        },
      },
      League.MLU: {
        Division.OPEN: {
          AgeBracket.NO_RESTRICTION: MLU_LIST_ID,
        },
      },
  }

  LIST_ID_TO_DIVISION = {
      USAU_COLLEGE_OPEN_LIST_ID: Division.OPEN,
      USAU_COLLEGE_WOMENS_LIST_ID: Division.WOMENS,
      USAU_CLUB_OPEN_LIST_ID: Division.OPEN,
      USAU_CLUB_WOMENS_LIST_ID: Division.WOMENS,
      USAU_CLUB_MIXED_LIST_ID: Division.MIXED,
      AUDL_LIST_ID: Division.OPEN,
      MLU_LIST_ID: Division.OPEN,
  }

  LIST_ID_TO_AGE_BRACKET = {
      USAU_COLLEGE_OPEN_LIST_ID: AgeBracket.COLLEGE,
      USAU_COLLEGE_WOMENS_LIST_ID: AgeBracket.COLLEGE,
      USAU_CLUB_OPEN_LIST_ID: AgeBracket.NO_RESTRICTION,
      USAU_CLUB_WOMENS_LIST_ID: AgeBracket.NO_RESTRICTION,
      USAU_CLUB_MIXED_LIST_ID: AgeBracket.NO_RESTRICTION,
      AUDL_LIST_ID: AgeBracket.NO_RESTRICTION,
      MLU_LIST_ID: AgeBracket.NO_RESTRICTION,
  }

  LIST_ID_TO_LEAGUE = {
      USAU_COLLEGE_OPEN_LIST_ID: League.USAU,
      USAU_COLLEGE_WOMENS_LIST_ID: League.USAU,
      USAU_CLUB_OPEN_LIST_ID: League.USAU,
      USAU_CLUB_WOMENS_LIST_ID: League.USAU,
      USAU_CLUB_MIXED_LIST_ID: League.USAU,
      AUDL_LIST_ID: League.AUDL,
      MLU_LIST_ID: League.MLU,
  }

  @staticmethod
  def GetListId(division, age_bracket, league):
    """Looks up the list_id which corresponds to the given division and league.

    Args:
      division: Division of interest
      age_bracket: AgeBracket of interest
      league: League of interest

    Returns:
      The list id corresponding to that league and division, or '' if no such
      list exists.
    """
    d = ListIdBiMap.LIST_ID_MAP.get(league, {})
    if not d:
      return ''
    d = d.get(division, {})
    if not d:
      return ''
    return d.get(age_bracket, '')

  @staticmethod
  def GetStructuredPropertiesForList(list_id):
    """Returns the division, age_bracket, and league for the given list id.

    Defaults to Division.OPEN, AgeBracket.NO_RESTRICTION, and League.USAU,
    if the division, age_bracket, or leauge, respectively, does not exist in
    the map for the given list_id.

    Args:
      list_id: ID of list for which to retrieve properties.

    Returns:
      (division, age_bracket, league) tuple for the given list ID.
    
    """
    division = ListIdBiMap.LIST_ID_TO_DIVISION.get(list_id, Division.OPEN)
    age_bracket = ListIdBiMap.LIST_ID_TO_AGE_BRACKET.get(list_id, AgeBracket.NO_RESTRICTION)
    league = ListIdBiMap.LIST_ID_TO_LEAGUE.get(list_id, League.USAU)

    return (division, age_bracket, league)

