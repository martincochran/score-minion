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

class ScoreReporterTestdata(object):
  """Utility class to load sample score reporter pages."""

  _TEST_URL_MAP = {
      # List of current tournaments.
      'tournament/?ViewAll=false&IsLeagueType=false&IsClinic=false&FilterByCategory=AE': 'testdata/current-tournaments-landing-page.html',

      # Tournament linked from that page.
      'East-New-England-Mens-Sectionals-2015/': 'testdata/east-new-england-mens-sectionals-landing.html',

      # Scores from that tournament.
      'East-New-England-Mens-Sectionals-2015/schedule/Men/Club-Men/': 'testdata/east-new-england-mens-sectionals-scores.html',

      # Landing page of tournament w/ multiple divisions.
      'USA-Ultimate-D-I-College-Championships-2015/': 'testdata/2015-D-I-college-championships-landing.html',

      # Scores from mens division.
      'USA-Ultimate-D-I-College-Championships-2015/schedule/Men/College-Men/': 'testdata/2015-D-I-college-championships-men.html',

      # EventTeam page linked from the scores page (Texas Men's)
      'teams/?EventTeamId=SUnYxthc9A4cEtl3q6%2fTSifiANLprghvMXhdM1%2b%2fw2Q%3d': 'testdata/texas-mens-team.html',

      # Team page linked from the EventTeam page
      'Eventteam/?TeamId=njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d': 'testdata/texas-mens-team-all-tournaments.html',

  }

  def GetTournamentListing(self):
    url = 'tournament/?ViewAll=false&IsLeagueType=false&IsClinic=false&FilterByCategory=AE'
    return open(self._TEST_URL_MAP[url], 'r').read()

  def GetLinkedTournamentLandingPage(self):
    url = 'East-New-England-Mens-Sectionals-2015/'
    return open(self._TEST_URL_MAP[url], 'r').read()

  def GetLinkedScoresPage(self):
    url = 'East-New-England-Mens-Sectionals-2015/schedule/Men/Club-Men/'
    return open(self._TEST_URL_MAP[url], 'r').read()

  def GetMultiDivisionTournamentLandingPage(self):
    url = 'USA-Ultimate-D-I-College-Championships-2015/'
    return open(self._TEST_URL_MAP[url], 'r').read()

  def GetMultiDivisionTournamentScoresPage(self):
    url = 'USA-Ultimate-D-I-College-Championships-2015/schedule/Men/College-Men/'
    return open(self._TEST_URL_MAP[url], 'r').read()

  def GetEventTeamPage(self):
    url = 'teams/?EventTeamId=SUnYxthc9A4cEtl3q6%2fTSifiANLprghvMXhdM1%2b%2fw2Q%3d'
    return open(self._TEST_URL_MAP[url], 'r').read()

  def GetTeamFullPage(self):
    url = 'Eventteam/?TeamId=njcj4s6Ct8EmLJyC98tkMEP3YQC5QiKs33MnNEu9jp0%3d'
    return open(self._TEST_URL_MAP[url], 'r').read()
