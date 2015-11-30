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
      taskqueue.add(url=url, method='GET',
          params={'name': tourney_name}, queue_name='score-reporter')


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
    # TODO: consider building the full URL to pass to
    # ParseTournamentInfo. Same as below for the call to 
    # ParseGameInfo.
    # TODO: look to see if tourney is already in DB. If not, then
    # parse the tourney info from the page (only want to do
    # rarely to avoid using Maps API). It's possible that the
    # tournament exists but the sub-division does not yet exist and
    # this needs to be handled gracefully (probably by just updating
    # the division in an atomic read/write transaction).

    # TODO: probably want to pass the name to this, because the full
    # URL cannot be determined just from the name passed here
    tourney_info = crawler.ParseTournamentInfo(response.content, url,
        enum_division, enum_age_bracket)

    # TODO: Lookup games in this time frame or that were crawled from this
    # score reporter URL.
    existing_games = []
    game_infos = crawler.ParseGameInfos(response.content, existing_games, url,
        enum_division, enum_age_bracket)

    team_tourney_ids = set()
    for game_info in game_infos:
      team_tourney_ids.add(game_info.home_team_link)
      team_tourney_ids.add(game_info.away_team_link)

      game = game_model.Game.FromGameInfo(game_info)

      db_game = game_model.game_key(game).get()
      if db_game:
        # TODO: update the relevant fields (teams, score, status, last_modified_at)
        # and update the game
        continue
      game.put()

    for team_tourney_id in team_tourney_ids:
      query = game_model.TeamIdLookup.query(
          game_model.TeamIdLookup.score_reporter_tourney_id == team_tourney_id)
      teams = query.fetch(1)
      if teams:
        continue
      taskqueue.add(url='/tasks/sr/crawl_team', method='GET',
          params={
            'id': team_tourney_id,
            'tourney_id': True,
            'division': division,
            'age_bracket': age_bracket,
          },
          queue_name='score-reporter')


class TeamHandler(webapp2.RequestHandler):
  def get(self):
    """Loads the team page and crawls it."""
    crawler = score_reporter_crawler.ScoreReporterCrawler()
    url = self.request.get('url', '')

    #content = # fetch the page

    team_info = crawler.GetTeamInfo(content)


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

