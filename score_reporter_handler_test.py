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

from datetime import datetime
import logging
import mock
import unittest
import webtest

import test_env_setup
from google.appengine.api import taskqueue

import game_model
import score_reporter_crawler
import score_reporter_handler
import score_reporter_testdata
import scores_messages
import web_test_base


# Fake landing page for the list of tournaments at play.usaultimate.com.
FAKE_LANDING_PAGE = """
<!doctype html> 
<body>
<a href="http://play.usaultimate.org/events/Womens-Sectionals-2015/">
women's sectionals
</a>
<a href="http://play.usaultimate.org/events/Mens-Sectionals-2015">
men's sectionals
</a>
</body>
"""


FAKE_TOURNEY_LANDING_PAGE = """
<!doctype html> 
<body>
<img id="CT_Main_0_imgEventLogo" src="/assets/1/15/EventLogoDimension/TCTLogo_510x340.jpg" />
<div class="eventInfo2">
  <b>City: </b>Easton<br /><b>Date: </b>3/31/2016 - 3/31/2016<br />
</div>
<dt class="groupTitle">
    Men's Schedule
</dt>
<input type="submit" value="College " class="btn" />
</body>
"""


FAKE_HS_TOURNEY_LANDING_PAGE = """
<!doctype html> 
<body>
<dt class="groupTitle">
    Boys Schedule
</dt>
<input type="submit" value="High School " class="btn" />
</body>
"""


FAKE_TOURNEY_SCORES_PAGE = """
<!doctype html> 
<body>
<tr data-game="71984">
  <span data-type="game-date">Fri 5/22</span>
  <span data-type="game-time">10:30 AM</span>
  <span data-type"game-field">Field 5</span>
  <span data-type="game-team-home">
    <a href="/events/teams/?EventTeamId=g%3d">Pittsburgh (1)</a>
  </span>
  <span data-type="game-team-away">
    <a href="/events/teams/?EventTeamId=8%3d">Georgia (8)</a>
  </span>
  <span data-type="game-score-home">15</span>
  <span data-type="game-score-away">13</span>
  <span data-type="game-status">Final</span>
</tr>
</body>
"""

FAKE_TOURNEY_NO_TEAM_URLS = """
<!doctype html> 
<body>
<tr data-game="71984">
  <span data-type="game-date">Fri 5/22</span>
  <span data-type="game-time">10:30 AM</span>
  <span data-type"game-field">Field 5</span>
  <span data-type="game-team-home">
  </span>
  <span data-type="game-team-away">
  </span>
  <span data-type="game-score-home">15</span>
  <span data-type="game-score-away">13</span>
  <span data-type="game-status">Final</span>
</tr>
</body>
"""


# These pages may have a valid division but they won't have an
# age bracket URL link.
FAKE_CLINIC_LANDING_PAGE = """
<!doctype html> 
<body>
<dt class="groupTitle">
    Mixed Schedule
</dt>
</body>
"""


FAKE_TEAM_INFO_PAGE = """
<!doctype html> 
<body>
	<div class="profile_info">
		<h4>
			<a id="CT_Main_0_ltlTeamName" href="http://play.usaultimate.org/teams/events/Eventteam/?TeamId=njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d">Texas (TUFF)</a>
		</h4>
		<p class="team_city">
			Austin,Texas
		</p>
		<dl>
			<dt>Competition Level:</dt>
			<dd>College</dd>
		</dl>
		<dl>
			<dt>Gender Division:</dt>
			<dd>Men's</dd>
		</dl>
		<dl>
			<dt>Head Coach:</dt>
			<dd>CALVIN LIN</dd>
		</dl>
		<dl>
			<dt>Asst.Coach:</dt>
			<dd>WILLIAM CAMPBELL</dd>
		</dl>
		<dl id="CT_Main_0_dlWebsite">
			<dt>Website:</dt>
			<dd><a id="CT_Main_0_lnkWebsite" href="http://texasultimate.wix.com/texasultimate" target="_blank">http://texasultimate.wix.com/texasultimate</a></dd>
		</dl>
        <dl id="CT_Main_0_dlFacebook">
			<dt>Facebook:</dt>
			<dd><a id="CT_Main_0_lnkFacebook" href="https://www.facebook.com/TexasUltimate">https://www.facebook.com/TexasUltimate</a></dd>
		</dl>
		<dl id="CT_Main_0_dlTwitter">
			<dt>Twitter:</dt>
			<dd><a id="CT_Main_0_lnkTwitter" href="modules/events/@texasultimate">@texasultimate</a></dd>
		</dl>
        <dl id="CT_Main_0_dlNotes">
			<dt>Notes:</dt>
			<dd>Captains - Chase Cunningham, Michael Hays

Head Coach - Calvin Lin
Assistant Coach - Will Campbell</dd>
		</dl>
	</div>
</body>
"""


class ScoreReporterHandlerTest(web_test_base.WebTestBase):
  def setUp(self):
    super(ScoreReporterHandlerTest, self).setUp()
    self.testapp = webtest.TestApp(score_reporter_handler.app)

  @mock.patch.object(taskqueue, 'add')
  def testParseLandingPage(self, mock_add_queue):
    self.SetHtmlResponse(FAKE_LANDING_PAGE)
    response = self.testapp.get('/tasks/sr/crawl')
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(2, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/sr/list_tournament_details', method='GET',
        params={'name': 'Womens-Sectionals-2015'},
        queue_name='score-reporter'))
    self.assertEquals(calls[1], mock.call(
        url='/tasks/sr/list_tournament_details', method='GET',
        params={'name': 'Mens-Sectionals-2015'},
        queue_name='score-reporter'))

  @mock.patch.object(taskqueue, 'add')
  def testParseLandingPage_noUrls(self, mock_add_queue):
    self.SetHtmlResponse('')
    response = self.testapp.get('/tasks/sr/crawl')
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testParseLandingPage_404(self, mock_add_queue):
    self.SetHtmlResponse('', 404)
    response = self.testapp.get('/tasks/sr/crawl')
    self.assertEqual(200, response.status_int)
    self.assertIn('not found', response.body)
    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyLandingPage(self, mock_add_queue):
    self.SetHtmlResponse(FAKE_TOURNEY_LANDING_PAGE)
    # Need to add the tourney URL to the URL as a parameter
    response = self.testapp.get(
        '/tasks/sr/list_tournament_details?name=my-tourney')
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/sr/crawl_tournament', method='GET',
        params={'url_suffix': 'schedule/Men/College-Men/',
          'name': 'my-tourney',
          'division': 'OPEN',
          'age_bracket': 'COLLEGE'},
        queue_name='score-reporter'))

    key = game_model.tourney_key_full('my-tourney')
    got_tourney = key.get()
    url = '%s/%s' % (
        'https://play.usaultimate.org',
        'assets/1/15/EventLogoDimension/TCTLogo_510x340.jpg')
    want_tourney = game_model.Tournament(
        key=key,
        url='%s%s' % (score_reporter_handler.USAU_URL_PREFIX, 'my-tourney'),
        start_date=datetime(2016, 3, 31, 0, 0),
        image_url_https=url,
        end_date=datetime(2016, 3, 31, 0, 0),
        id_str='my-tourney', name='my tourney',
        last_modified_at=got_tourney.last_modified_at,
        sub_tournaments=[game_model.SubTournament(
          division=scores_messages.Division.OPEN,
          age_bracket=scores_messages.AgeBracket.COLLEGE)
        ])
    self.assertEquals(got_tourney, want_tourney)

    # Crawl it again. There should still only be one tourney in the db.
    self.SetHtmlResponse(FAKE_TOURNEY_LANDING_PAGE)
    response = self.testapp.get(
        '/tasks/sr/list_tournament_details?name=my-tourney')
    self.assertEqual(200, response.status_int)
    all_tourneys = game_model.Tournament.query().fetch()
    self.assertEquals(1, len(all_tourneys))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyLandingPage_updateTourney(self, mock_add_queue):
    key = game_model.tourney_key_full('my-tourney')
    empty_tourney = game_model.Tournament(
        last_modified_at=datetime.utcnow(),
        key=key,
        url='%s%s' % (score_reporter_handler.USAU_URL_PREFIX, 'my-tourney'),
        id_str='my-tourney', name='my tourney')
    empty_tourney.put()

    self.SetHtmlResponse(FAKE_TOURNEY_LANDING_PAGE)
    # Need to add the tourney URL to the URL as a parameter
    response = self.testapp.get(
        '/tasks/sr/list_tournament_details?name=my-tourney')
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/sr/crawl_tournament', method='GET',
        params={'url_suffix': 'schedule/Men/College-Men/',
          'name': 'my-tourney',
          'division': 'OPEN',
          'age_bracket': 'COLLEGE'},
        queue_name='score-reporter'))

    got_tourney = key.get()
    # The tourney should now be updated with the new division that was added.
    want_tourney = game_model.Tournament(
        key=key,
        url='%s%s' % (score_reporter_handler.USAU_URL_PREFIX, 'my-tourney'),
        id_str='my-tourney', name='my tourney',
        start_date=datetime(2016, 3, 31, 0, 0),
        end_date=datetime(2016, 3, 31, 0, 0),
        last_modified_at=got_tourney.last_modified_at,
        sub_tournaments=[game_model.SubTournament(
          division=scores_messages.Division.OPEN,
          age_bracket=scores_messages.AgeBracket.COLLEGE)
        ])
    self.assertEquals(got_tourney, want_tourney)

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyLandingPage_updateTourneyNewDate(self, mock_add_queue):
    key = game_model.tourney_key_full('my-tourney')
    wrong_date_tourney = game_model.Tournament(
        last_modified_at=datetime.utcnow(),
        key=key,
        start_date=datetime(2016, 5, 31, 0, 0),
        end_date=datetime(2016, 5, 31, 0, 0),
        sub_tournaments=[game_model.SubTournament(
          division=scores_messages.Division.OPEN,
          age_bracket=scores_messages.AgeBracket.COLLEGE)
        ],
        url='%s%s' % (score_reporter_handler.USAU_URL_PREFIX, 'my-tourney'),
        id_str='my-tourney', name='my tourney')
    wrong_date_tourney.put()

    self.SetHtmlResponse(FAKE_TOURNEY_LANDING_PAGE)
    # Need to add the tourney URL to the URL as a parameter
    response = self.testapp.get(
        '/tasks/sr/list_tournament_details?name=my-tourney')
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(1, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/sr/crawl_tournament', method='GET',
        params={'url_suffix': 'schedule/Men/College-Men/',
          'name': 'my-tourney',
          'division': 'OPEN',
          'age_bracket': 'COLLEGE'},
        queue_name='score-reporter'))

    got_tourney = key.get()
    # The tourney should now be updated with the new division that was added.
    want_tourney = game_model.Tournament(
        key=key,
        url='%s%s' % (score_reporter_handler.USAU_URL_PREFIX, 'my-tourney'),
        id_str='my-tourney', name='my tourney',
        start_date=datetime(2016, 3, 31, 0, 0),
        end_date=datetime(2016, 3, 31, 0, 0),
        last_modified_at=got_tourney.last_modified_at,
        sub_tournaments=[game_model.SubTournament(
          division=scores_messages.Division.OPEN,
          age_bracket=scores_messages.AgeBracket.COLLEGE)
        ])
    self.assertEquals(got_tourney, want_tourney)

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyLandingPage_badNameParam(self, mock_add_queue):
    # Need to add the tourney name as a parameter. If it's not
    # present no crawling should take place.
    response = self.testapp.get('/tasks/sr/list_tournament_details')
    self.assertEquals(0, response.body.find('No tournament name specified'))
    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyLandingPage_404(self, mock_add_queue):
    self.SetHtmlResponse('', 404)
    response = self.testapp.get(
        '/tasks/sr/list_tournament_details?name=no_name')
    self.assertEqual(200, response.status_int)
    self.assertEquals(0, response.body.find('Tourney page not found'))
    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyLandingPage_clinic(self, mock_add_queue):
    """Ensure clinics or other non-tourneys are not crawled."""
    self.SetHtmlResponse(FAKE_CLINIC_LANDING_PAGE)
    response = self.testapp.get(
        '/tasks/sr/list_tournament_details?name=my_tourney')
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyLandingPage_noCollegeOrClubDivision(self, mock_add_queue):
    """Ensure a tourney with no club or college divisions is not crawled."""
    self.SetHtmlResponse(FAKE_HS_TOURNEY_LANDING_PAGE)
    response = self.testapp.get(
        '/tasks/sr/list_tournament_details?name=my_tourney')
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyScores_newTourneyOneTeamKnown(self, mock_add_queue):
    # Page with two teams, one of which has been added to the DB.
    self.SetHtmlResponse(FAKE_TOURNEY_SCORES_PAGE)
    params = {
        'url_suffix': 'schedule/Men/College-Men/',
        'name': 'my_tourney',
        'division': 'OPEN',
        'age_bracket': 'COLLEGE'
    }
    # One team has already been added to the database, but one is new.
    game_model.TeamIdLookup(
        score_reporter_id='123',
        score_reporter_tourney_id=['8%3d']).put()
    response = self.testapp.get('/tasks/sr/crawl_tournament', params=params)
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls

    # Team page should be crawled for the unknown team.
    self.assertEquals(1, len(calls))
    self.assertEquals(calls[0], mock.call(
        url='/tasks/sr/crawl_team', method='GET',
        params={'id': 'g%3d',
          'division': 'OPEN',
          'age_bracket': 'COLLEGE'},
        queue_name='score-reporter'))

    full_url = '%s%s' % (score_reporter_crawler.EVENT_PREFIX,
        'my_tourney/schedule/Men/College-Men/')
    game_query = game_model.Game.query()
    games = game_query.fetch(1000)
    self.assertEqual(0, len(games))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyScores_newTourneyBothTeamsKnown(self, mock_add_queue):
    # Page with two teams, both of which have been added to the DB.
    self.SetHtmlResponse(FAKE_TOURNEY_SCORES_PAGE)
    params = {
        'url_suffix': 'schedule/Men/College-Men/',
        'name': 'my-tourney',
        'division': 'OPEN',
        'age_bracket': 'COLLEGE'
    }
    # One team has already been added to the database, but one is new.
    game_model.TeamIdLookup(
        score_reporter_id='123',
        score_reporter_tourney_id=['8%3d']).put()
    game_model.Team(twitter_id=5,
        score_reporter_id='123').put()
    game_model.TeamIdLookup(
        score_reporter_id='456',
        score_reporter_tourney_id=['g%3d']).put()
    response = self.testapp.get('/tasks/sr/crawl_tournament', params=params)
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

    full_url = '%s%s' % (score_reporter_crawler.EVENT_PREFIX,
        'my_tourney/schedule/Men/College-Men/')
    game_query = game_model.Game.query()
    games = game_query.fetch(1000)
    self.assertEqual(1, len(games))
    self.assertEqual(scores_messages.Division.OPEN, games[0].division)
    self.assertEqual(scores_messages.AgeBracket.COLLEGE, games[0].age_bracket)
    self.assertEqual('71984', games[0].id_str)
    self.assertEqual('my-tourney', games[0].tournament_id)
    self.assertEqual('my tourney', games[0].tournament_name)
    self.assertEqual([15, 13], games[0].scores)
    self.assertEqual('456', games[0].teams[0].score_reporter_id)
    self.assertEqual('123', games[0].teams[1].score_reporter_id)
    self.assertEqual(None, games[0].teams[0].twitter_id)
    self.assertEqual(5, games[0].teams[1].twitter_id)

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyScores_noTeamUrls(self, mock_add_queue):
    # Page with two teams, both of which have been added to the DB.
    self.SetHtmlResponse(FAKE_TOURNEY_NO_TEAM_URLS)
    params = {
        'url_suffix': 'schedule/Men/College-Men/',
        'name': 'my_tourney',
        'division': 'OPEN',
        'age_bracket': 'COLLEGE'
    }
    # One team has already been added to the database, but one is new.
    game_model.TeamIdLookup(
        score_reporter_id='123',
        score_reporter_tourney_id=['8%3d']).put()
    game_model.Team(twitter_id=5,
        score_reporter_id='123').put()
    game_model.TeamIdLookup(
        score_reporter_id='456',
        score_reporter_tourney_id=['g%3d']).put()
    response = self.testapp.get('/tasks/sr/crawl_tournament', params=params)
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))
    game_query = game_model.Game.query()
    games = game_query.fetch(1000)
    self.assertEqual(0, len(games))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyScores_updateDate(self, mock_add_queue):
    # Page with two teams, one of which has been added to the DB.
    self.SetHtmlResponse(FAKE_TOURNEY_SCORES_PAGE)
    params = {
        'url_suffix': 'schedule/Men/College-Men/',
        'name': 'my_tourney',
        'division': 'OPEN',
        'age_bracket': 'COLLEGE'
    }
    # Both teams and the game have already been added to the database.
    game_model.TeamIdLookup(
        score_reporter_id='123',
        score_reporter_tourney_id=['8%3d']).put()
    game_model.TeamIdLookup(
        score_reporter_id='456',
        score_reporter_tourney_id=['g%3d']).put()
    game_info = score_reporter_crawler.GameInfo(
        '71984', 'tourney_id', 'my_tourney', scores_messages.Division.OPEN,
        scores_messages.AgeBracket.COLLEGE)
    game_info.status = 'Unknown'
    game = game_model.Game.FromGameInfo(game_info, {})
    self.assertEquals(scores_messages.GameStatus.UNKNOWN, game.game_status)
    game.put()
    response = self.testapp.get('/tasks/sr/crawl_tournament', params=params)
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

    db_game = game_model.game_key(game).get()
    self.assertEquals(scores_messages.GameStatus.FINAL, db_game.game_status)
 
  @mock.patch.object(score_reporter_handler, 'FetchUsauPage')
  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyScores_urlEncoded(self, mock_add_queue, mock_fetch_page):
    self.SetHtmlResponse(FAKE_TOURNEY_SCORES_PAGE)
    params = {
        'url_suffix': 'schedule%2FWomen%2FClub-Women%2F',
        'name': 'US-Open-Ultimate-Championships-2015%2F',
        'division': 'WOMENS',
        'age_bracket': 'NO_RESTRICTION'
    }
    response = self.testapp.get('/tasks/sr/crawl_tournament', params=params)
    self.assertEqual(200, response.status_int)
    calls = mock_fetch_page.mock_calls

    self.assertEqual(calls[0], mock.call(
      'US-Open-Ultimate-Championships-2015//schedule/Women/Club-Women/'))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyScores_badParams(self, mock_add_queue):
    response = self.testapp.get('/tasks/sr/crawl_tournament',
        params={'url_suffix': 'schedule/Men/College-Men/'})
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyScores_badEnumParsing(self, mock_add_queue):
    params = {
        'url_suffix': 'schedule%2FWomen%2FClub-Women%2F',
        'name': 'US-Open-Ultimate-Championships-2015%2F',
        'division': 'BAD_ENUM',
        'age_bracket': 'NO_RESTRICTION'
    }
    response = self.testapp.get('/tasks/sr/crawl_tournament', params=params)
    self.assertEqual(200, response.status_int)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  @mock.patch.object(taskqueue, 'add')
  def testParseTourneyScores_404(self, mock_add_queue):
    self.SetHtmlResponse('', 404)
    params = {
        'url_suffix': 'schedule%2FWomen%2FClub-Women%2F',
        'name': 'US-Open-Ultimate-Championships-2015%2F',
        'division': 'WOMENS',
        'age_bracket': 'NO_RESTRICTION'
    }
    response = self.testapp.get('/tasks/sr/crawl_tournament', params=params)
    self.assertEqual(200, response.status_int)
    self.assertIn('not found', response.body)

    calls = mock_add_queue.mock_calls
    self.assertEquals(0, len(calls))

  def testShouldUpdateGame_status(self):
    handler = score_reporter_handler.TournamentScoresHandler()
    db_game = game_model.Game()
    incoming_game = game_model.Game()
    db_game.scores = [0, 0]
    incoming_game.scores = [0, 0]
    db_game.sources = [game_model.GameSource(
        type=scores_messages.GameSourceType.SCORE_REPORTER)]
    incoming_game.sources = [game_model.GameSource(
        type=scores_messages.GameSourceType.SCORE_REPORTER)]
    self.assertFalse(handler._ShouldUpdateGame(db_game, incoming_game))

    db_game.game_status = scores_messages.GameStatus.FINAL
    self.assertTrue(handler._ShouldUpdateGame(db_game, incoming_game))

  def testShouldUpdateGame_scores(self):
    handler = score_reporter_handler.TournamentScoresHandler()
    db_game = game_model.Game()
    incoming_game = game_model.Game()
    db_game.scores = [1, 2]
    incoming_game.scores = [1, 2]
    db_game.sources = [game_model.GameSource(
        type=scores_messages.GameSourceType.SCORE_REPORTER)]
    incoming_game.sources = [game_model.GameSource(
        type=scores_messages.GameSourceType.SCORE_REPORTER)]
    self.assertFalse(handler._ShouldUpdateGame(db_game, incoming_game))
    incoming_game.scores[1] = 3
    self.assertTrue(handler._ShouldUpdateGame(db_game, incoming_game))

  def testParseTeamInfo_sanity(self):
    self._runParseTeamTest()

  def testParseTeamInfo_twitterUserExists(self):
    """Ensure if User exists, the Team will be updated with twitter ID."""
    self.CreateUser(4, 'texasultimate').put()
    self._runParseTeamTest(twitter_id=4)

  def testParseTeamInfo_teamMapExists(self):
    """If TeamIdLookup exists, nothing is changed."""
    id = 'njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d'
    tourney_id = 'g%3d'
    id_map = game_model.TeamIdLookup(
        score_reporter_id=id,
        score_reporter_tourney_id=[tourney_id])
    id_map.put()
    self._runParseTeamTest()

  def testParseTeamInfo_teamMapExistsWithoutTourney(self):
    """TeamIdLookup exists, but doesn't contain the crawled tourney."""
    id = 'njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d'
    id_map = game_model.TeamIdLookup(
        score_reporter_id=id,
        score_reporter_tourney_id=[])
    id_map.put()
    self._runParseTeamTest()

  def testParseTeamInfo_srTeamExists(self):
    """Don't update db if Team with this sr ID already exists."""
    id = 'njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d'
    team = game_model.Team.get_or_insert(id,
        score_reporter_id=id)
    self._runParseTeamTest()

  def testParseTeamInfo_fullTeamInfoExists(self):
    """Don't update db with FullTeamInfo if it already exist."""
    id = 'njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d'
    key = game_model.full_team_info_key(id)
    team_info = score_reporter_crawler.TeamInfo()
    team_info.facebook_url = 'https://www.facebook.com/TexasUltimate'
    team_info.name = 'Texas (TUFF)'
    team_info.website = 'http://texasultimate.wix.com/texasultimate'
    team_info.id = id
    team_info.twitter_screenname = 'texasultimate'
    info_pb = game_model.FullTeamInfo.FromTeamInfo(team_info,
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.COLLEGE,
        key=key)
    info_pb.put()
    self._runParseTeamTest()

  def testParseTeam_404(self):
    self.SetHtmlResponse('', 404)
    params = {
        'id': 'g%3d',
        'division': 'OPEN',
        'age_bracket': 'COLLEGE',
    }
    response = self.testapp.get('/tasks/sr/crawl_team', params=params)
    self.assertEqual(200, response.status_int)
    self.assertIn('not found', response.body)

  def testParseTeam_badEnum(self):
    self.SetHtmlResponse('', 200)
    params = {
        'id': 'g%3d',
        'division': 'OPEN',
        'age_bracket': 'BAD_ENUM',
    }
    response = self.testapp.get('/tasks/sr/crawl_team', params=params)
    self.assertEqual(200, response.status_int)

  def _runParseTeamTest(self, twitter_id=None):
    self.SetHtmlResponse(FAKE_TEAM_INFO_PAGE)
    params = {
        'id': 'g%3d',
        'division': 'OPEN',
        'age_bracket': 'COLLEGE',
    }
    response = self.testapp.get('/tasks/sr/crawl_team',
        params=params)
    self.assertEqual(200, response.status_int)
    id = 'njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d'

    # 1. Check the Team info in the datastore
    query = game_model.Team.query()
    teams = query.fetch(1000)
    self.assertEqual(1, len(teams))

    # Full team ID as crawled from FAKE_TEAM_INFO_PAGE.
    self.assertEqual(id, teams[0].score_reporter_id)
    self.assertEqual(twitter_id, teams[0].twitter_id)

    # 2. Check the FullTeamInfo in the datastore
    query = game_model.FullTeamInfo.query()
    teams = query.fetch(1000)
    self.assertEqual(1, len(teams))
    key = game_model.full_team_info_key(id)
    self.assertEqual(
        'https://www.facebook.com/TexasUltimate', teams[0].facebook_url)
    self.assertEqual(
        scores_messages.AgeBracket.COLLEGE, teams[0].age_bracket)
    self.assertEqual(
        scores_messages.Division.OPEN, teams[0].division)
    self.assertEqual('Texas (TUFF)', teams[0].name)
    self.assertEqual('texasultimate', teams[0].screen_name)
    self.assertEqual(
        'http://texasultimate.wix.com/texasultimate', teams[0].website)
    self.assertEqual(
        id, teams[0].id)

    # 3. Check the TeamIdLookup in the datastore
    query = game_model.TeamIdLookup.query()
    items = query.fetch(1000)
    self.assertEqual(1, len(items))

    self.assertEqual(id, items[0].score_reporter_id)
    self.assertEqual(1, len(items[0].score_reporter_tourney_id))
    self.assertEqual('g%3d', items[0].score_reporter_tourney_id[0])
