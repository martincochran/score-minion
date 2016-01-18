#!/usr/bin/env python
#
# Copyright 2016 Martin Cochran
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

import unittest
import webtest

import test_env_setup

from google.appengine.ext import testbed

import game_model
import team_editor
import tweets
import web_test_base


class TeamEditorTest(web_test_base.WebTestBase):
  def setUp(self):
    super(TeamEditorTest, self).setUp()
    self.testapp = webtest.TestApp(team_editor.app)

    game_model.Team(
        score_reporter_id='%3d').put()
    game_model.Team(
        score_reporter_id='%8d').put()

  def tearDown(self):
    # Reset the URL stub to the original function
    self.testbed.deactivate()

  def testSanityGet_viewTeams(self):
    response = self.testapp.get('/teams/view')
    self.assertEqual(200, response.status_int)
    # URL params are encoded.
    self.assertIn('%253d', response.body)
    self.assertIn('%258d', response.body)

  def testSanityGet_editTeam(self):
    game_model.FullTeamInfo(
        id='%3d', name='bruisers').put()
    response = self.testapp.get('/teams/edit?id=%253d')
    self.assertEqual(200, response.status_int)
    self.assertIn('%253d', response.body)
    self.assertIn('bruisers', response.body)
    # Verify the USAU link is present.
    self.assertIn('Eventteam', response.body)

  def testSanityPost(self):
    game_model.FullTeamInfo(
        id='%3d', name='bruisers').put()
    params = {
      'id': '%253d',
      'screen_name': 'bruisers',
    }
    
    # Need to fake the response from Twitter for UserList.
    content_items = [
        '"id_str":"2525"',
        '"id":2525',
        '"screen_name":"bruisers"',
    ]
    self.return_content = ['[{%s}]' % ','.join(content_items)]

    response = self.testapp.post('/teams/edit', params=params)
    self.assertEqual(200, response.status_int)
    self.assertIn('%3d', response.body)
    self.assertIn('2525', response.body)

    teams = game_model.Team.query(game_model.Team.twitter_id == 2525).fetch(1)
    self.assertEqual(1, len(teams))
