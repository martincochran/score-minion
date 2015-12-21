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
    # TODO: if this is a 404, don't throw an error since it's unlikely
    # that error will change with retries
    raise FetchError(e)

  if response.status_code != 200:
    raise FetchError('Response code not 200: %s, %s' % (response.status_code,
        response.content))
  return response


class ScoreReporterHandler(webapp2.RequestHandler):

  # Landing page for score reporter tournaments.
  MAIN_URL = ('tournament/?ViewAll=false&IsLeagueType='
      'false&IsClinic=false&FilterByCategory=AE')

  def get(self):
    """Loads the main event page and schedules crawling of all tournaments."""
    response = FetchUsauPage(self.MAIN_URL)

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
  def get(self):
    """Schedules crawling for each division on the tourney landing page."""
    url = self.request.get('name', '')
    if not url:
      msg = 'No tournament name specified'
      logging.warning(msg)
      self.response.write(msg)
      return

    response = FetchUsauPage(url)

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
  def get(self):
    """Crawls the scores from the given tournament."""
    url = self.request.get('url_suffix', '')
    name = self.request.get('name', '')
    division = self.request.get('division', '')
    age_bracket = self.request.get('age_bracket', '')
    
    if not division or not age_bracket:
      msg = 'Division or age bracket not specified'
      logging.warning(msg)
      self.response.write(msg)
      return

    # TODO: perhaps run this in a try/catch block
    enum_division = scores_messages.Division(division)
    enum_age_bracket = scores_messages.AgeBracket(age_bracket)

    # TODO: do something with name
    if not url or not name:
      msg = 'URL or name not specified'
      logging.warning(msg)
      self.response.write(msg)
      return

    url = urllib2.unquote(url)
    name = urllib2.unquote(name)
    response = FetchUsauPage('%s/%s' % (name, url))

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

    team_tourney_ids = set()
    for game_info in game_infos:
      team_tourney_ids.add(self._ParseTourneyId(game_info.home_team_link))
      team_tourney_ids.add(self._ParseTourneyId(game_info.away_team_link))

      game = game_model.Game.FromGameInfo(game_info)

      db_game = game_model.game_key(game).get()
      if db_game:
        # TODO: update the relevant fields (teams, score, status,
        # last_modified_at) and update the game
        continue
      game.put()

    # TODO: do this before writing the game to the DB. Add the team
    # info to the game if it exists.
    for team_tourney_id in team_tourney_ids:
      query = game_model.TeamIdLookup.query(
          game_model.TeamIdLookup.score_reporter_tourney_id == team_tourney_id)
      teams = query.fetch(1)
      if teams:
        continue
      taskqueue.add(url='/tasks/sr/crawl_team', method='GET',
          params={
            'id': team_tourney_id,
            'division': division,
            'age_bracket': age_bracket,
          },
          queue_name='score-reporter')
  
  def _ParseTourneyId(self, link):
    return link.split('=')[1]


class TeamHandler(webapp2.RequestHandler):
  def get(self):
    """Loads the team page and crawls it."""
    id = self.request.get('id', '')
    division = self.request.get('division', '')
    age_bracket = self.request.get('age_bracket', '')

    enum_division = scores_messages.Division(division)
    enum_age_bracket = scores_messages.AgeBracket(age_bracket)

    crawler = score_reporter_crawler.ScoreReporterCrawler()
    response = FetchUsauPage('/teams/?EventTeamId=%s' % id)
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
    #
    # In either case, update the FullTeamInfo score reporter data if
    # appropriate.
    logging.info('querying user: %s', team_info.twitter_screenname)
    query = tweets.User.query(
        tweets.User.screen_name == team_info.twitter_screenname)
    users = query.fetch(1)

    # TODO: refactor this logic to make it clearer
    # We know about this team via Twitter.
    if users:
      twitter_id = users[0].id_64
      query = game_model.Team.query(
          game_model.Team.twitter_id == twitter_id)
      teams = query.fetch(1)
      if teams:
        # Everything is updated, return.
        if teams[0].score_reporter_id:
          return
        # Update score reporter id.
        teams[0].score_reporter_id = team_info.id
        teams[0].put
      else:
        team = game_model.Team(
            twitter_id=users[0].id_64,
            score_reporter_id=team_info.id)
        team.put()
      return
    # We don't know the user.
    query = game_model.Team.query(
        game_model.Team.score_reporter_id == team_info.id)
    teams = query.fetch(1)
    if teams:
      return
    team = game_model.Team(score_reporter_id=team_info.id)
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
      # TODO: check to see if fields have changed and update.
      return

    info_pb = game_model.FullTeamInfo.FromTeamInfo(team_info,
        division, age_bracket, key=key)
    info_pb.put()


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

