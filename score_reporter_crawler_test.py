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
import logging
import unittest

import test_env_setup

from google.appengine.ext import testbed
from google.appengine.ext import ndb

import game_model
import score_reporter_crawler
import score_reporter_testdata
import scores_messages


class ScoreReporterCrawlerTest(unittest.TestCase):
  def setUp(self):
    """Stub out the datastore."""
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()

    self.crawler = score_reporter_crawler.ScoreReporterCrawler()
    self.testdata = score_reporter_testdata.ScoreReporterTestdata()

  def testParseTournaments(self):
    content = self.testdata.GetTournamentListing()
    urls = sorted(list(self.crawler.ParseTournaments(content)))
    self.assertEqual(48, len(urls))

    # Test a couple values
    prefix = score_reporter_crawler.EVENT_PREFIX
    self.assertEqual('%s2015-GUM-Club-Challenge-Clinics' % prefix,
        urls[0])
    self.assertEqual('%s2015-Learn-to-Play-Ultimate-Registration' % prefix,
        urls[1])

  def testGetDivisions(self):
    content = self.testdata.GetLinkedTournamentLandingPage()
    self.assertEqual([(scores_messages.Division.OPEN,
      scores_messages.AgeBracket.NO_RESTRICTION, 'schedule/Men/Club-Men/')],
      self.crawler.GetDivisions(content))

    content = self.testdata.GetMultiDivisionTournamentLandingPage()
    self.assertEqual([
      (scores_messages.Division.OPEN, scores_messages.AgeBracket.COLLEGE,
        'schedule/Men/College-Men/'),
      (scores_messages.Division.WOMENS, scores_messages.AgeBracket.COLLEGE,
        'schedule/Women/College-Women/')],
      self.crawler.GetDivisions(content))

  def testParseTournamentInfo(self):
    """Verify we can parse the correct tourney info from the landing page."""
    url = 'http://a'
    content = self.testdata.GetLinkedTournamentLandingPage()
    start_date = datetime.datetime.strptime('8/29/2015', '%M/%d/%Y')
    end_date = datetime.datetime.strptime('8/30/2015:8', '%M/%d/%Y:%H')

    expected_subtourney = game_model.SubTournament(
        age_bracket=scores_messages.AgeBracket.NO_RESTRICTION,
        division=scores_messages.Division.OPEN)
    expected_sectionals = game_model.Tournament(
        id_str='', name='East New England Men\'s Sectionals', url=url,
        sub_tournaments=[expected_subtourney],
        start_date=start_date, end_date=end_date)
    actual_sectionals = self.crawler.ParseTournamentInfo(content, url,
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION)
    self.assertFalse('' == actual_sectionals.id_str)
    expected_sectionals.id_str = actual_sectionals.id_str
    self.assertEqual(expected_sectionals, actual_sectionals)

    content = self.testdata.GetMultiDivisionTournamentLandingPage()
    start_date = datetime.datetime.strptime('5/22/2015', '%M/%d/%Y')
    end_date = datetime.datetime.strptime('5/23/2015:8', '%M/%d/%Y:%H')
    expected_nationals = game_model.Tournament(
        id_str='', name='USA Ultimate D-I College Championships', url=url,
        sub_tournaments=[expected_subtourney],
        start_date=start_date, end_date=end_date)
    actual_nationals = self.crawler.ParseTournamentInfo(content, url,
        scores_messages.Division.OPEN, scores_messages.AgeBracket.COLLEGE)

    self.assertFalse('' == actual_nationals.id_str)
    expected_nationals.id_str = actual_nationals.id_str
    expected_sectionals.sub_tournaments[0].age_bracket = scores_messages.AgeBracket.COLLEGE
    self.assertEqual(expected_nationals, actual_nationals)

  def testParseGameInfos_singleDivision(self):
    content = self.testdata.GetLinkedScoresPage()
    existing_games = []
    name = 'East-New-England-Mens-Sectionals-2015'
    url = '%s/%s' % (name, '/schedule/Men/Club-Men/')
    actual_games =  self.crawler.ParseGameInfos(content, existing_games, url,
        name, scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION)

    # No placement brackets for this tournament.
    self.assertEqual(31, len(actual_games))

    # Verify full parsing of one pool play game.
    full_url = '%s/%s' % (score_reporter_crawler.EVENT_PREFIX, url)
    game = score_reporter_crawler.GameInfo('83210', full_url, name,
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION)
    game.date = 'Sat 8/29'
    game.time = '9:30 AM'
    game.field = 'TBA'
    game.home_team = 'Garuda (1)'
    game.away_team = 'Birds of Pray (9)'
    game.home_team_link = '/events/teams/?EventTeamId=WO6CSqOhIVnYrxZG2nJOyxJxTe96hKyt4GWPoKUJW4c%3d'
    game.away_team_link = '/events/teams/?EventTeamId=ibuw7QYAoDrkmXWO3HCnY%2fB1SZIPhrbsQg4X3bDuOEs%3d'
    game.home_team_score = 'W'
    game.away_team_score = 'F'
    game.status = 'Final'
    game.pool_name = 'Pool A'
    self.assertEqual(game, actual_games[0])

    # Verify full parsing of one bracket game.
    game = score_reporter_crawler.GameInfo('83230', full_url, name,
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.NO_RESTRICTION)
    game.date = '8/30/2015 11:30 AM'
    game.time = ''
    game.field = ''
    game.home_team = 'Garuda (1)'
    game.away_team = 'Big Wrench (2)'
    game.home_team_link = '/events/teams/?EventTeamId=WO6CSqOhIVnYrxZG2nJOyxJxTe96hKyt4GWPoKUJW4c%3d'
    game.away_team_link = '/events/teams/?EventTeamId=i2gXqMBL623tnaB43nuvMx5d33XJ9RmPFjiSa0qm71U%3d'
    game.home_team_score = '12'
    game.away_team_score = '9'
    game.status = ''
    game.bracket_title = 'Finals'
    self.assertEqual(game, actual_games[20])

  def testParseGameInfos_multipleDivisions(self):
    content = self.testdata.GetMultiDivisionTournamentScoresPage()
    existing_games = []
    name = 'USA-Ultimate-D-I-College-Championships-2015'
    url = '%s/%s' % (name, 'schedule/Men/College-Men/')
    full_url = '%s/%s' % (score_reporter_crawler.EVENT_PREFIX, url)
    actual_games = self.crawler.ParseGameInfos(content, existing_games,
        full_url, name, scores_messages.Division.OPEN,
        scores_messages.AgeBracket.COLLEGE)

    self.assertEqual(55, len(actual_games))
    logging.info(actual_games)

    # Verify full parsing of one pool play game.
    game = score_reporter_crawler.GameInfo('71984', full_url, name,
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.COLLEGE)
    game.date = 'Fri 5/22'
    game.time = '10:30 AM'
    game.field = 'Field 5'
    game.home_team = 'Pittsburgh (1)'
    game.away_team = 'Georgia (8)'
    game.home_team_link = '/events/teams/?EventTeamId=Ug2uww1laX%2fVPnLB4r7NDl1RNuJQDCPPw2VZWOlDT4g%3d'
    game.away_team_link = '/events/teams/?EventTeamId=f0uATWXWUuVmOhU5qFwpseoRjhiJrnkc89NyoAjJEK8%3d'
    game.home_team_score = '15'
    game.away_team_score = '13'
    game.pool_name = 'Pool A'
    game.status = 'Final'
    self.assertEqual(game, actual_games[0])

    # Verify full parsing of one bracket game.
    game = score_reporter_crawler.GameInfo('72034', full_url, name,
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.COLLEGE)
    game.date = '5/25/2015 2:30 PM'
    game.time = ''
    game.field = 'Field 1'
    game.home_team = 'Oregon (15)'
    game.away_team = 'North Carolina (3)'
    game.home_team_link = '/events/teams/?EventTeamId=4mXGp3TuNpmoqX2WhNX%2brhtHIQgY1ZmciKxhCQXvYnk%3d'
    game.away_team_link = '/events/teams/?EventTeamId=Uv5epkn9IFbchnmKHlhisIf%2f5TcR6KZCp4%2brQZ3hMGU%3d'
    game.home_team_score = '6'
    game.away_team_score = '15'
    game.status = ''
    game.bracket_title = 'Finals'
    self.assertEqual(game, actual_games[40])

    # Verify full parsing of one placement bracket game.
    game = score_reporter_crawler.GameInfo('72047', full_url, name,
        scores_messages.Division.OPEN,
        scores_messages.AgeBracket.COLLEGE)
    game.date = '5/24/2015 8:30 AM'
    game.time = ''
    game.field = 'Field 11'
    game.home_team = 'Wisconsin (12)'
    game.away_team = 'Cornell (20)'
    game.home_team_link = '/events/teams/?EventTeamId=eKtMX5hrmQxMbFhIQXxm0gEWJfYEz%2fxBm4iKkiZ9qlM%3d'
    game.away_team_link = '/events/teams/?EventTeamId=R2JcuXLUduzb0Y0%2fQFPQyiSjWzkSeS4mFY8xdoCasds%3d'
    game.home_team_score = '15'
    game.away_team_score = '12'
    game.status = ''
    game.bracket_title = 'Placement Game #1'
    self.assertEqual(game, actual_games[51])

  def testGetTeamInfo(self):
    content = self.testdata.GetEventTeamPage()
    expected_team_info = score_reporter_crawler.TeamInfo()
    expected_team_info.name = 'Texas (TUFF)'
    expected_team_info.city = 'Austin,Texas'
    expected_team_info.facebook_url = 'https://www.facebook.com/TexasUltimate'
    expected_team_info.twitter_screenname = 'texasultimate'
    expected_team_info.website = 'http://texasultimate.wix.com/texasultimate'
    expected_team_info.age_bracket = 'College'
    expected_team_info.division = 'Men\'s'
    expected_team_info.id = 'njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d'
    self.assertEqual(expected_team_info, self.crawler.GetTeamInfo(content))

    # Check loading the full team page
    content = self.testdata.GetTeamFullPage()
    self.assertEqual(expected_team_info, self.crawler.GetTeamInfo(content))

  def testTeamInfoParser(self):
    parser = score_reporter_crawler.TeamInfoParser()

    expected_values = [
        ('subzeroultimate', 'https://twitter.com/SubZeroUltimate'),
        ('madisonclub', 'MadisonClub'),
        ('txshowdown', 'https://twitter.com/txshowdown'),
        ('texasultimate', '@texasultimate'),
        ('', ''),
    ]
    for k, v in expected_values:
      self.assertEqual(k, parser.parse_twitter_screen_name(v))
 
if __name__ == '__main__':
  unittest.main()
