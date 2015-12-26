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

import logging
import urllib2
import webapp2

from google.appengine.api import taskqueue
from google.appengine.api import urlfetch

import game_model
import score_reporter_crawler
import scores_messages
import tweets

USAU_URL_PREFIX = 'https://play.usaultimate.org/events/'
FETCH_DEADLINE_SECS = 30


class FetchError(Exception):
  """Any error that occurred with fetching data from SR."""
  pass


def FetchUsauPage(url):
  """Wrapper around urlfetch for the given USAU url.

  Args:
    url: URL suffix for USA page.
  Returns:
    The urlfetch.Result object from the fetch.
  Raises:
    FetchError on any error raised by the fetch.
  """
  try:
    full_url = '%s%s' % (USAU_URL_PREFIX, url)
    logging.info('Fetching %s', full_url)
    response = urlfetch.fetch(full_url, deadline=FETCH_DEADLINE_SECS)
  except urlfetch.Error as e:
    logging.warning('Could not fetch URL %s: %s', full_url, e)
    raise FetchError(e)

  if response.status_code not in [200, 404]:
    raise FetchError('Response code not 200/404: %s, %s' % (response.status_code,
        response.content))
  return response


class ScoreReporterHandler(webapp2.RequestHandler):
  """Handler for /tasks/sr/crawl."""

  # Landing page for score reporter tournaments.
  MAIN_URL = ('tournament/?ViewAll=false&IsLeagueType='
      'false&IsClinic=false&FilterByCategory=AE')

  def get(self):
    """Loads the main event page and schedules crawling of all tournaments."""
    response = FetchUsauPage(self.MAIN_URL)
    if response.status_code != 200:
      WriteError('Response code not 200 - page %s not found' % self.MAIN_URL,
          self.response)
      return

    crawler = score_reporter_crawler.ScoreReporterCrawler()
    tournaments = crawler.ParseTournaments(response.content)

    url = '/tasks/sr/list_tournament_details'
    for tourney in tournaments:
      logging.info('tourney: %s', tourney)
      tourney_name = tourney[len(score_reporter_crawler.EVENT_PREFIX):]
      # Strip off trailing '/'
      if tourney_name[-1] == '/':
        tourney_name = tourney_name[:-1]
      taskqueue.add(url=url, method='GET',
          params={'name': tourney_name}, queue_name='score-reporter')
    msg = 'Scheduled crawling for the following URLs:\n%s' % '\n'.join(tournaments)
    self.response.write(msg)


class TournamentLandingPageHandler(webapp2.RequestHandler):
  """Handler for /tasks/sr/list_tournament_details."""
  def get(self):
    """Schedules crawling for each division on the tourney landing page."""
    url = self.request.get('name', '')
    if not url:
      WriteError('No tournament name specified', self.response)
      return

    response = FetchUsauPage(url)
    if response.status_code != 200:
      WriteError('Tourney page not found', self.response)
      return

    crawler = score_reporter_crawler.ScoreReporterCrawler()
    tournaments = crawler.GetDivisions(response.content)

    crawl_url = '/tasks/sr/crawl_tournament'
    for tourney_info in tournaments:
      logging.info('tourney_info: %s', tourney_info)
      taskqueue.add(url=crawl_url, method='GET',
          params={'url_suffix': tourney_info[2], 'name': url,
            'division': tourney_info[0].name,
            'age_bracket': tourney_info[1].name},
          queue_name='score-reporter')
      # If the tournament hasn't been crawled yet - OR -
      # the tournament isn't current for some definition of current,
      # add task to crawl the scores in that tournament.


class TournamentScoresHandler(webapp2.RequestHandler):
  """Handler for /tasks/sr/crawl_tournament."""
  def get(self):
    """Crawls the scores from the given tournament."""
    url = self.request.get('url_suffix', '')
    name = self.request.get('name', '')
    division = self.request.get('division', '')
    age_bracket = self.request.get('age_bracket', '')
    
    if not division or not age_bracket:
      WriteError('Division or age bracket not specified', self.response)
      return

    try: 
      enum_division = scores_messages.Division(division)
      enum_age_bracket = scores_messages.AgeBracket(age_bracket)
    except TypeError as e:
      logging.error('Could not parse params as enum: %s', e)
      return

    if not url or not name:
      WriteError('URL or name not specified', self.response)
      return

    url = urllib2.unquote(url)
    name = urllib2.unquote(name)
    response = FetchUsauPage('%s/%s' % (name, url))
    if response.status_code != 200:
      WriteError('Response code not 200 - page %s/%s not found' % (name, url),
          self.response)
      return

    crawler = score_reporter_crawler.ScoreReporterCrawler()
    # TODO: look to see if tourney is already in DB. If not, then
    # parse the tourney info from the page (only want to do
    # rarely to avoid using Maps API). It's possible that the
    # tournament exists but the sub-division does not yet exist and
    # this needs to be handled gracefully (probably by just updating
    # the division in an atomic read/write transaction).
    full_url = '%s/%s' % (name, url)
    tourney_info = crawler.ParseTournamentInfo(response.content, full_url,
        enum_division, enum_age_bracket)

    # TODO: Lookup games in this time frame or that were crawled from this
    # score reporter URL.
    existing_games = []
    game_infos = crawler.ParseGameInfos(response.content, existing_games,
        full_url, name, enum_division, enum_age_bracket)

    for game_info in game_infos:
      self._HandleGame(game_info, enum_division, enum_age_bracket)

  def _HandleGame(self, game_info, division, age_bracket):
    """Check and maybe update the parsed game info object against the datastore .

    Args:
      game_info: score_reporter_crawler.GameInfo object.
      division: scores_messages.Division division of team
      age_bracket: scores_messages.AgeBracket age bracket of team
    """
    team_tourney_ids = set()
    team_tourney_ids.add((self._ParseTourneyId(game_info.home_team_link),
      game_info.home_team_link))
    team_tourney_ids.add((self._ParseTourneyId(game_info.away_team_link),
      game_info.away_team_link))

    team_tourney_map = {}
    found_all = True
    for team_tourney_id, url in team_tourney_ids:
      query = game_model.TeamIdLookup.query(
          game_model.TeamIdLookup.score_reporter_tourney_id == team_tourney_id)
      teams = query.fetch(1)
      if teams:
        team_tourney_map[url] = teams[0].score_reporter_id
        continue
      found_all = False
      taskqueue.add(url='/tasks/sr/crawl_team', method='GET',
          params={
            'id': team_tourney_id,
            'division': '%s' % division,
            'age_bracket': '%s' % age_bracket,
          }, queue_name='score-reporter')

    # If all the teams are not in the database yet, wait until they are crawled
    # so we can add the team's canonical ID (rather than the
    # tournament-specific ID).
    if not found_all:
      logging.info('Did not find all teams in db for %s', game_info.tourney_id)
      return

    # OK - both teams are known and game should be added to DB if it
    # is new or updated.
    game = game_model.Game.FromGameInfo(game_info, team_tourney_map)
    db_game = game_model.game_key(game).get()
    if self._ShouldUpdateGame(db_game, game):
      game.put()

  def _ShouldUpdateGame(self, db_game, incoming_game):
    """Returns true if any fields in incoming_game are more recent than db_game.

    Both game objects refer to the same data (same score reporter game ID).

    Args:
      db_game: Game info from the database
      incoming_game: Parsed game from the page.
    """
    # If the game is not in the datastore yet, definitely update it.
    if not db_game:
      return True
    if incoming_game.game_status != db_game.game_status:
      return True
    # TODO: this isn't correct. If a Twitter update occurs after a SR update,
    # this will always overwrite the Twitter score.
    for i in range(len(incoming_game.scores)):
      if incoming_game.scores[i] != db_game.scores[i]:
        return True
    # TODO: update game if the main team ids are now known (as opposed to just
    # the tourney-specific ids)
    return False
  
  def _ParseTourneyId(self, link):
    return link.split('=')[1]


class TeamHandler(webapp2.RequestHandler):
  """Handler for /tasks/sr/crawl_team."""
  def get(self):
    """Loads the team page and crawls it."""
    id = self.request.get('id', '')
    division = self.request.get('division', '')
    age_bracket = self.request.get('age_bracket', '')

    try:
      enum_division = scores_messages.Division(division)
      enum_age_bracket = scores_messages.AgeBracket(age_bracket)
    except TypeError as e:
      logging.error('Could not parse params as enum: %s', e)
      return

    crawler = score_reporter_crawler.ScoreReporterCrawler()
    response = FetchUsauPage('/teams/?EventTeamId=%s' % id)
    if response.status_code != 200:
      WriteError('Response code not 200 - team %s not found' % id,
          self.response)
      return
    team_info = crawler.GetTeamInfo(response.content)

    # Add the team to the database, if appropriate.
    # Associate the tourney URL with the team URL
    self._PossiblyAddTeamLookup(team_info.id, id)
    self._PossiblyStoreTeam(team_info)
    self._PossiblyStoreFullTeamInfo(team_info, enum_division, enum_age_bracket)

    # TODO: consider crawling the full team's page to get all games they've
    # played in.

  def _PossiblyAddTeamLookup(self, team_id, tourney_id):
    """Add the mapping between tourney ID and full team ID if needed.

    Args:
      team_id: ID for team page with all games.
      tourney_id: ID for tournament-specific team page.
    """
    query = game_model.TeamIdLookup.query(
        game_model.TeamIdLookup.score_reporter_id == team_id)
    teams = query.fetch(1)
    if not teams:
      id_map = game_model.TeamIdLookup(
          score_reporter_id=team_id,
          score_reporter_tourney_id=[tourney_id])
      id_map.put()
      return

    # If the team entry exists, make sure this tourney is associated with it.
    if tourney_id in teams[0].score_reporter_tourney_id:
      return
    teams[0].score_reporter_tourney_id.append(tourney_id)
    teams[0].put()

  def _PossiblyStoreTeam(self, team_info):
    """Update team's association w/ Twitter users, if needed.

    Args:
      team_info: score_reporter_crawler.TeamInfo object
    """
    # The team may have come in via Twitter or score reporter so we need to
    # join the two sources.
    # 1. Lookup that team's Twitter ID in the User DB. Update score reporter
    #    ID if appropriate and return.
    # 2. If the Twitter ID is not found, that means this is a team not yet
    #    being crawled by Twitter. Add a Team entry with SR ID and move on.
    team = game_model.Team.get_or_insert(
        team_info.id, score_reporter_id=team_info.id)
    if not team_info.twitter_screenname or team.twitter_id:
      return

    logging.debug('querying user: %s', team_info.twitter_screenname)
    query = tweets.User.query(
        tweets.User.screen_name == team_info.twitter_screenname)
    users = query.fetch(1)
    if users:
      team.twitter_id = users[0].id_64
      team.put()
  
  def _PossiblyStoreFullTeamInfo(self, team_info, division, age_bracket):
    """If we don't know about this team, update the FullTeamInfo.

    Args:
      team_info: score_reporter_crawler.TeamInfo object
      division: scores_messages.Division division of team
      age_bracket: scores_messages.AgeBracket age bracket of team
    """
    key = game_model.full_team_info_key(team_info.id)
    info_pb = key.get()
    if info_pb:
      # TODO(P2): check to see if fields have changed and update.
      return

    info_pb = game_model.FullTeamInfo.FromTeamInfo(team_info,
        division, age_bracket, key=key)
    info_pb.put()


def WriteError(msg, response):
  """Convenience function to both log and write an error message.

  Args:
    msg: Error message to be logged and written to the response.
    response: response object.
  """
  logging.error(msg)
  response.write(msg)


app = webapp2.WSGIApplication([
  # Initiates the crawl of all upcoming or active tournaments.
  ('/tasks/sr/crawl', ScoreReporterHandler),
  # Lists the sub-tournaments for a given tournament.
  ('/tasks/sr/list_tournament_details', TournamentLandingPageHandler),
  # Parses the tournament details and all games.
  ('/tasks/sr/crawl_tournament', TournamentScoresHandler),
  # Crawls the team details from the tournament.
  ('/tasks/sr/crawl_team', TeamHandler),
  ], debug=True)

