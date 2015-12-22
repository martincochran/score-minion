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
import logging
import uuid

from HTMLParser import HTMLParser

import game_model
import scores_messages


# URL prefix for all USAU tournaments.
EVENT_PREFIX = 'http://play.usaultimate.org/events/'


class GameInfo(object):
  """Text-only representation of the game in score reporter."""

  def __init__(self, id, tourney_id, name, division, age_bracket):
    """Builds GameInfo object.

    Args:
      id: Unique ID of game, supplied by score reporter
      tourney_id: Full tournament URL for this division / age bracket
      name: Name of tournament (part of URL)
      division: scores_messages.Division value
      age_bracket: scores_messages.AgeBracket value
    """
    self.id = id
    self.created_at = datetime.utcnow()
    self.division = division
    self.age_bracket = age_bracket
    self.tourney_id = tourney_id
    self.tourney_name = name
    self.date = ''
    self.time = ''
    self.field = ''
    self.home_team = ''
    self.away_team = ''
    self.home_team_link = ''
    self.away_team_link = ''
    self.home_team_score = ''
    self.away_team_score = ''
    self.status = ''
    self.pool_name = ''
    self.bracket_title = ''

  def __str__(self):
    return 'Game %s (%s): %s vs %s (pool/bracket: %s%s), %s-%s on %s %s, %s\n%s\n%s' % (
        self.id, self.status, self.home_team, self.away_team,
        self.pool_name, self.bracket_title,
        self.home_team_score, self.away_team_score, self.date, self.time,
        self.field, self.home_team_link, self.away_team_link)

  def __repr__(self):
    return self.__str__()

  def __cmp__(self, other):
    if not other:
      return

    if self.id != other.id:
      return cmp(self.id, other.id)
    if self.date != other.date:
      return cmp(self.date, other.date)
    if self.time != other.time:
      return cmp(self.time, other.time)
    if self.field != other.field:
      return cmp(self.field, other.field)
    if self.home_team != other.home_team:
      return cmp(self.home_team, other.home_team)
    if self.away_team != other.away_team:
      return cmp(self.away_team, other.away_team)
    if self.home_team_link != other.home_team_link:
      return cmp(self.home_team_link, other.home_team_link)
    if self.away_team_link != other.away_team_link:
      return cmp(self.away_team_link, other.away_team_link)
    if self.home_team_score != other.home_team_score:
      return cmp(self.home_team_score, other.home_team_score)
    if self.away_team_score != other.away_team_score:
      return cmp(self.away_team_score, other.away_team_score)
    if self.status != other.status:
      return cmp(self.status, other.status)
    if self.status != other.status:
      return cmp(self.status, other.status)
    if self.pool_name != other.pool_name:
      return cmp(self.pool_name, other.pool_name)
    if self.bracket_title != other.bracket_title:
      return cmp(self.bracket_title, other.bracket_title)
    if self.division != other.division:
      return cmp(self.division, other.division)
    if self.age_bracket != other.age_bracket:
      return cmp(self.age_bracket, other.age_bracket)
    return 0


class TeamInfo(object):
  """Text-only representations of the Team as parsed from SR."""

  def __init__(self):
    self.id = ''
    self.name = ''
    self.city = ''
    self.age_bracket = ''
    self.division = ''
    self.website = ''
    self.twitter_screenname = ''
    self.facebook_url = ''
    # TODO: consider these fields as well
    # self.coach = ''
    # self.asst_coach = ''

  def __str__(self):
    return 'Team %s (%s): %s, %s, %s, %s\n%s\n%s' % (
        self.name, self.id, self.city, self.age_bracket,
        self.division, self.website, self.twitter_screenname, self.facebook_url)

  def __repr__(self):
    return self.__str__()

  def __cmp__(self, other):
    if not other:
      return

    if self.id != other.id:
      return cmp(self.id, other.id)
    if self.name != other.name:
      return cmp(self.name, other.name)
    if self.city != other.city:
      return cmp(self.city, other.city)
    if self.age_bracket != other.age_bracket:
      return cmp(self.age_bracket, other.age_bracket)
    if self.division != other.division:
      return cmp(self.division, other.division)
    if self.website != other.website:
      return cmp(self.website, other.website)
    if self.twitter_screenname != other.twitter_screenname:
      return cmp(self.twitter_screenname, other.twitter_screenname)
    if self.facebook_url != other.facebook_url:
      return cmp(self.facebook_url, other.facebook_url)
    return 0


class ScoreReporterCrawler(object):
  """Class to handle the crawling and parsing of Score Reporter data.

  Currently only College- and Club-division data is parsed.
  """

  def ParseTournaments(self, content):
    """Returns the listed tournaments for the current tournaments page.

    Args:
      content: Full HTML contents of the current tournaments page.

    Returns:
      A list of urls of the found tournaments.
    """
    parser = TournamentUrlParser()
    parser.feed(content)
    return parser.get_urls()

  def GetDivisions(self, content):
    """Returns the divisions for the given tourney landing page.

    Args:
      content: Full HTML contents of tourney landing page.

    Returns:
      A list of (division, url) pairs of the divisions found in the contents.
    """
    parser = DivisionParser()
    parser.feed(content)
    return parser.get_divisions()

  def ParseTournamentInfo(self, content, url, division, age_bracket):
    """Parses the tournament info.

    Args:
      content: Full HTML contents of tourney landing page.
      url: URL of tourney landing page.
      division: Text-format of Division protobuf ('OPEN', eg)
      age_bracket: Text-format of AgeBracket protobuf ('COLLEGE', eg)

    Returns:
      game_model.Tournament object that can be used for interacting with the
      datastore objects. Namely, the ID is unique and will be consistently
      returned for the same tournament.
    """
    parser = TournamentInfoParser()
    parser.feed(content)
    tournament_id = 'tourney_%s' % str(uuid.uuid4())

    city, state = parser.get_location()

    # TODO: make call to Maps API to get geo pt.
    #   *OR* use URL from FieldMap link. But only do this if the
    #   tournament (or sub-tournament) is new. In crawling a tourney
    #   like nationals, first one division will be added and then
    #   other divisions need to be added correctly.
    tourney = game_model.Tournament(id_str=tournament_id,
        name=parser.get_name(),
        sub_tournaments=[game_model.SubTournament(
          division=scores_messages.Division(division),
          age_bracket=scores_messages.AgeBracket(age_bracket))
        ],
        url=url)

    date_fmt_str = '%M/%d/%Y'
    # TODO(use date/time appropriate for location)
    if parser.get_start_date():
      tourney.start_date = datetime.strptime(
          parser.get_start_date(), date_fmt_str)

    # The end date needs to be after all the games are done.
    delta = timedelta(days=1, hours=8)
    if parser.get_end_date():
      tourney.end_date = datetime.strptime(
          parser.get_end_date(), date_fmt_str) + delta

    return tourney

  def ParseGameInfos(self, content, existing_games, url, name, division,
      age_bracket):
    """Parses the games and scores for them for all games on the page.

    Args:
      content: Full HTML contents of the tourney scores page.
      existing_games: Existing games in this time period.
      url: URL of tourney scores page.
      name: Name of tournament (part of URL)
      division: Division of this game
      age_bracket: Age bracket of the game.
    Returns:
      A list of GameInfo objects.
    """
    full_url = '%s%s' % (EVENT_PREFIX, url)
    parser = GameInfosParser(full_url, name, division, age_bracket)
    parser.feed(content)
    return parser.get_games()

  def GetTeamInfo(self, content):
    """Parses the team info from the team info page content.

    Args:
      content: Full HTML content from the EventTeamId page. This is the page
        with team scores only for a given tournament, not to be confused with
        the team page with the team ID in the URL and all the team scores from
        the season.
    Returns:
      The game_model.Team object with the inferred team information.
    """
    parser = TeamInfoParser()
    parser.feed(content)
    return parser.get_team_info()


class TournamentUrlParser(HTMLParser):
  """Parses the tournaments listed from the current events page."""

  def __init__(self):
    HTMLParser.__init__(self)
    self._urls = []

  def handle_starttag(self, tag, attrs):
    if not tag == 'a':
      return
    url = ''
    for tag, value in attrs:
      if tag != 'href':
        continue

      if value.find(EVENT_PREFIX) != -1:
        url = value

    if url:
      # Don't worry about the two general landing pages.
      tourney_name = url[len(EVENT_PREFIX):-1]
      if tourney_name in ['tournament', 'league']:
        return
      self._urls.append(url)

  def get_urls(self):
    return set(self._urls)


class DivisionParser(HTMLParser):
  """Parses the divisions and their URL suffixes from the page."""

  def __init__(self):
    HTMLParser.__init__(self)
    self._divisions = []
    self._age_brackets = []
    self._urls = []
    self._copy_data = False

  def handle_starttag(self, tag, attrs):
    # Tags of interest
    tags = ['dt', 'input']
    if tag not in tags:
      return
    if tag == 'dt':
      for tag, value in attrs:
        if tag != 'class':
          continue

        if value == 'groupTitle':
          self._copy_data = True
    if tag == 'input':
      for tag, value in attrs:
        if tag == 'type' and value != 'submit':
          return

      for tag, value in attrs:
        if tag == 'value':
          added_division = False
          # Parse the age bracket
          if value.strip() == 'College':
            added_division = True
            self._age_brackets.append(scores_messages.AgeBracket.COLLEGE)
          if value.strip() == 'Club':
            added_division = True
            self._age_brackets.append(scores_messages.AgeBracket.NO_RESTRICTION)
          # TODO: handle other age brackets
          if not added_division:
            return

          # At this point we have the age bracket and the division: build the URL.
          self._urls.append(
              self._BuildUrl(self._divisions[-1], self._age_brackets[-1]))
          return
          
  def handle_data(self, data):
    if not self._copy_data:
      return
    self._copy_data = False

    if data.find('Women') != -1:
      self._divisions.append(scores_messages.Division.WOMENS)
      return
    if data.find('Men') != -1:
      self._divisions.append(scores_messages.Division.OPEN)
      return
    if data.find('Mixed') != -1:
      self._divisions.append(scores_messages.Division.MIXED)
      return

  def get_divisions(self):
    logging.info('divisions: %s', self._divisions)
    logging.info('age brackets: %s', self._age_brackets)
    logging.info('urls: %s', self._urls)
    return zip(self._divisions, self._age_brackets, self._urls)

  def _BuildUrl(self, division, age_bracket):
    """Builds the tournament URL suffix for the given division.

    Args:
      division: Division of the tournament.
      age_bracket: Age Bracket of the tournaent.
    Returns:
      The URL suffix for that division of the tournament.
      eg, 'schedule/Men/College-Men/'
    """
    str_fmt = 'schedule/%s/%s-%s/'

    div = 'Women'
    if division == scores_messages.Division.OPEN:
      div = 'Men'
    if division == scores_messages.Division.MIXED:
      div = 'Mixed'

    age_brak = 'College'
    if age_bracket == scores_messages.AgeBracket.NO_RESTRICTION:
      age_brak = 'Club'

    return str_fmt % (div, age_brak, div)
  


class TournamentInfoParser(HTMLParser):
  """Parses the tournament info from the page."""

  _TAGS_OF_INTEREST = ['h1', 'div', 'b']

  def __init__(self):
    HTMLParser.__init__(self)
    # Name of the tournament.
    self._name = ''

    # Datetime: start of tournament.
    self._start_date = ''

    # Datetime: end of tournament (after all games are done).
    self._end_date = ''

    # Location.
    self._city = ''
    self._state = ''

    self._in_tag = {}

    self._prior_data = ''

    for tag in self._TAGS_OF_INTEREST:
      self._in_tag[tag] = False

  def handle_starttag(self, tag, attrs):
    if tag not in self._TAGS_OF_INTEREST:
      return
    self._in_tag[tag] = True

    # We are only interested in h1 tags with the right value of 'class'.
    if tag == 'h1':
      for attr, value in attrs:
        if attr == 'class' and value == 'page_header':
          return

      self._in_tag[tag] = False

    # We are only interested in div tags with the right value of 'class'.
    if tag == 'div':
      for attr, value in attrs:
        if attr == 'class' and value == 'eventInfo2':
          return

      self._in_tag[tag] = False

  def handle_endtag(self, tag):
    self._in_tag[tag] = False
         
  def handle_data(self, data):
    if self._in_tag['h1']:
      self._name = data

    # The only pieces of info we want are in the 'div' of interest.
    if not self._in_tag['div']:
      return

    if self._in_tag['b']:
      self._prior_data = data
      return

    if self._prior_data.find('City') != -1:
      self._city = data
      self._prior_data = ''
      return

    if self._prior_data.find('Date') != -1:
      self._prior_data = ''
      dates = data.split('-')
      if len(dates) < 2:
        logging.info('Dates not found in data: %s', data)
        return
      self._start_date = dates[0].strip()
      self._end_date = dates[0].strip()
      return

    if self._prior_data.find('State') != -1:
      self._prior_data = ''
      self._state = data
      return

  def get_name(self):
    return self._name

  def get_start_date(self):
    return self._start_date

  def get_end_date(self):
    return self._end_date

  def get_location(self):
    return (self._city, self._state)


class GameInfosParser(HTMLParser):
  """Parses the scores from each game."""

  _TAGS_OF_INTEREST = ['table', 'tr', 'span', 'a', 'div', 'h4', 'th']

  def __init__(self, url, name, division, age_bracket):
    HTMLParser.__init__(self)
    self.division = division
    self.age_bracket = age_bracket
    self.url = url
    self.name = name
    self.games = []
    self.last_data_type = ''
    self.in_pool_play_scores_table = False
    self.in_bracket = False
    self.in_bracket_title = False
    self.bracket_title = ''
    self.pool_name = ''

    self._in_tag = {}
    for tag in self._TAGS_OF_INTEREST:
      self._in_tag[tag] = False

  def handle_starttag(self, tag, attrs):
    if tag not in self._TAGS_OF_INTEREST:
      return
    self._in_tag[tag] = True
    if tag == 'table':
      for name, value in attrs:
        if name == 'class' and value.find('scores_table') != -1:
          self.in_pool_play_scores_table = True

    if tag == 'tr':
      for name, value in attrs:
        # New game, add it to the list.
        if name == 'data-game':
          self.games.append(
              GameInfo(value, self.url, self.name, self.division,
                self.age_bracket))
          self.games[-1].pool_name = self.pool_name
          return

    if tag == 'span':
      for name, value in attrs:
        # Special-case the missing '=' in the 'game-field' tag for
        # pool play games.
        if name.find('data-type"') != -1:
          self.last_data_type = 'game-field'
          return

        # We need to special case the field and date for bracket games.
        if name == 'class' and self.in_bracket:
          if value == 'location':
            self.last_data_type = 'game-field'
            return
          # This is a combination date / time as opposed to the separate fields
          # for pool play games.
          if value == 'date':
            self.last_data_type = 'game-date'
            return

        if name == 'data-type':
          self.last_data_type = value.strip()
          return

    if tag == 'div':
      for name, value in attrs:
        if name == 'class' and value.strip() == 'bracket_col':
          self.in_bracket = True
        if name == 'id' and value.find('game') != -1:
          # IDs are different in bracket games. They are of the form
          # 'game12345' where '12345' is the game id.
          self.games.append(
              GameInfo(value[4:], self.url, self.name, self.division,
                self.age_bracket))
          self.games[-1].bracket_title = self.bracket_title
          return

    if tag == 'h4':
      for name, value in attrs:
        if name == 'class' and value.strip() == 'col_title':
          self.in_bracket_title = True

    if tag == 'a':
      href = ''
      for name, value in attrs:
        if name == 'href':
          href = value
      if self.last_data_type == 'game-team-home':
        self.games[-1].home_team_link = href
      if self.last_data_type == 'game-team-away':
        self.games[-1].away_team_link = href

  def handle_endtag(self, tag):
    if tag not in self._TAGS_OF_INTEREST:
      return
    self._in_tag[tag] = False

    # If we're done with the game, clear the saved state about the data type
    # to avoid parsing info we're not interested in.
    if tag == 'tr':
      self.last_data_type = ''
    if tag == 'table':
      logging.debug('out of table')
      self.in_pool_play_scores_table = False

    if tag == 'h4':
      self.in_bracket_title = False
         
  def handle_data(self, data):
    if self.in_bracket_title:
      self.bracket_title = data.strip()

    # If we're not in a bracket do some filtering.
    if not self.in_bracket:
      if not (self.in_pool_play_scores_table or self._in_tag['tr']):
        return

    if not data.strip():
      return

    if self._in_tag['th'] and data.find('Pool') == 0:
      logging.debug('data w/ Pool: %s', data)
      self.pool_name = data[0:6]

    if self._in_tag['span']:
      if self.last_data_type == 'game-date':
        self.games[-1].date = data.strip()
        self.last_data_type = ''
        return
      if self.last_data_type == 'game-time':
        self.games[-1].time = data.strip()
        self.last_data_type = ''
        return
      # Blurg - there is a typo so this won't work.
      if self.last_data_type == 'game-field':
        self.games[-1].field = data.strip()
        self.last_data_type = ''
        return
      if self.last_data_type == 'game-team-home':
        self.games[-1].home_team = data.strip()
        self.last_data_type = ''
        return
      if self.last_data_type == 'game-team-away':
        self.games[-1].away_team = data.strip()
        self.last_data_type = ''
        return
      if self.last_data_type == 'game-score-home':
        self.games[-1].home_team_score = data.strip()
        self.last_data_type = ''
        return
      if self.last_data_type == 'game-score-away':
        self.games[-1].away_team_score = data.strip()
        self.last_data_type = ''
        return
      if self.last_data_type == 'game-status':
        self.games[-1].status = data.strip()
        self.last_data_type = ''
        return


  def get_games(self):
    return self.games


class TeamInfoParser(HTMLParser):
  """Parses the team info from the team page (main or tourney)."""

  _TAGS_OF_INTEREST = ['div', 'p', 'dd', 'dt', 'a', 'h4', 'form', 'body']

  def __init__(self):
    HTMLParser.__init__(self)
    self.games = []
    self.last_data_type = ''
    self.in_team_info_div = False
    self.in_website = False
    self.in_twitter_screenname = False
    self.in_facebook_url = False
    self.dt_data = ''
    self.team_info = TeamInfo()
    self.team_id_url = ''

    self._in_tag = {}
    for tag in self._TAGS_OF_INTEREST:
      self._in_tag[tag] = False

  def handle_starttag(self, tag, attrs):
    if tag not in self._TAGS_OF_INTEREST:
      return
    self._in_tag[tag] = True
    if tag == 'div':
      for name, value in attrs:
        if name == 'class' and value.find('profile_info') != -1:
          self.in_team_info_div = True

    # If we're not in the team div, ignore everything else.
    if not (self.in_team_info_div or self._in_tag['body']):
      return

    if tag == 'a':
      for name, value in attrs:
        if name == 'id':
          # New game, add it to the list.
          if value.find('CT_Main_0_lnkWebsite') != -1:
            self.in_website = True
          if value.find('CT_Main_0_lnkTwitter') != -1:
            self.in_twitter_screenname = True
          if value.find('CT_Main_0_lnkFacebook') != -1:
            self.in_facebook_url = True

    # Check for the team ID on the event team info page.
    if tag == 'a' and self._in_tag['h4']:
      href = ''
      in_team_id_url = False
      for name, value in attrs:
        if name == 'href':
          href = value
        if name == 'id' and value.find('CT_Main_0_ltlTeamName') != -1:
          in_team_id_url = True
      if in_team_id_url and href:
        self.team_id_url = href

    if tag == 'form':
      href = ''
      for name, value in attrs:
        if name == 'action':
          href = value
      if href:
        logging.debug('found team url: %s', href)
        self.team_id_url = href

    if tag == 'p':
      for name, value in attrs:
        if name == 'class' and value.find('team_city') != -1:
          self.in_city_tag = True

  def handle_endtag(self, tag):
    if not self.in_team_info_div:
      return

    if tag not in self._TAGS_OF_INTEREST:
      return
    self._in_tag[tag] = False

    # If we're done with the game, clear the saved state about the data type
    # to avoid parsing info we're not interested in.
    if tag == 'a':
      self.in_facebook_url = False
      self.in_website = False
      self.in_twitter_screenname = False

    # Parse the ID from the team URL if it was found.
    if self.team_id_url:
      idx = self.team_id_url.find('=')
      if idx != -1:
        self.team_info.id = self.team_id_url[idx+1:]
      self.team_id_url = ''

    if tag == 'div':
      logging.debug('out of table')
      self.in_team_info_div = False
         
  def handle_data(self, data):
    if not self.in_team_info_div:
      return

    if self._in_tag['h4'] and data.strip():
      logging.debug('in team name: %s', data)
      self.team_info.name = data.strip()
      return

    if self._in_tag['dt']:
      self.dt_data = data.strip()
      return

    if self._in_tag['dd']:
      if self.dt_data.find('Competition Level') != -1:
        self.team_info.age_bracket = data.strip()
        self.dt_data = ''
      if self.dt_data.find('Gender Division') != -1:
        self.team_info.division = data.strip()
        self.dt_data = ''

    if self._in_tag['a']:
      if self.in_website:
        self.team_info.website = data.strip()
        return
      if self.in_twitter_screenname:
        self.team_info.twitter_screenname = self.parse_twitter_screen_name(data)
        return
      if self.in_facebook_url:
        self.team_info.facebook_url = data.strip()
        return

    if self._in_tag['p'] and self.in_city_tag:
      self.team_info.city = data.strip()
      self.in_city_tag = False

  def parse_twitter_screen_name(self, data):
    if not data:
      return data
    data = data.strip().lower()
    if data[0] == '@':
      return data[1:]
    return data.split('/')[-1]

  def get_team_info(self):
    return self.team_info
