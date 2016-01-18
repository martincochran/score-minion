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
#

import os
import logging
import urllib2

from google.appengine.api import users

import game_model
import oauth_token_manager
import twitter_fetcher

import jinja2
import webapp2


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


# URL prefix for the team URL page.
TEAM_PREFIX = 'http://play.usaultimate.org/teams/events/Eventteam/?TeamId='


class TeamListHandler(webapp2.RequestHandler):
  """Lists teams with no associated Twitter ID."""
  def get(self):
    query = game_model.Team.query(
        game_model.Team.twitter_id == None)
    teams = query.fetch(50)

    # Double-quote the team IDs to get around automatic un-quoting
    # by template framework.
    for team in teams:
      team.score_reporter_id = urllib2.quote(team.score_reporter_id)

    template_values = {
      'teams': teams,
    }

    template = JINJA_ENVIRONMENT.get_template('html/team_editor.html')
    self.response.write(template.render(template_values))


class TeamEditorHandler(webapp2.RequestHandler):
  """Displays a form to add a Twitter ID to a team's info."""
  def get(self):
    sr_id = self.request.get('id', '')
    logging.info('sr_id = %s', sr_id)

    query = game_model.FullTeamInfo.query(
        game_model.FullTeamInfo.id == sr_id)
    team_infos = query.fetch(1)
    if not team_infos:
      self.response.write('Team for ID %s not found.' % sr_id)
      return

    team_info = team_infos[0]

    full_url = '%s%s' % (TEAM_PREFIX, sr_id)
    
    twitter_tmpl = 'https://www.google.com/search?q=%s'
    twitter_search_url = twitter_tmpl % urllib2.quote(
        team_info.name + ' ultimate site:twitter.com')
    template_values = {
      'sr_id': urllib2.quote(team_info.id),
      'name': team_info.name,
      'screen_name': team_info.screen_name,
      'team_link': full_url,
      'twitter_search': twitter_search_url,
    }

    template = JINJA_ENVIRONMENT.get_template('html/team_single_edit.html')
    self.response.write(template.render(template_values))

  def post(self):
    id = self.request.get('id', '')
    screen_name = self.request.get('screen_name', '')

    id = urllib2.unquote(id)
    query = game_model.Team.query(
        game_model.Team.score_reporter_id == id)
    teams = query.fetch(1)

    if not teams:
      self.response.write('Could not look up team info for %s' % id)
      return
    team = teams[0]

    # Lookup id w/ given screen name using twitter_fetcher.
    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)
    try:
      json_obj = fetcher.LookupUsers(screen_name, use_screen_name=True)
    except twitter_fetcher.FetchError as e:
      msg = 'Could not lookup users %s, %s' % (screen_name, e)
      logging.warning(msg)
      self.response.write(msg)
      return

    if not json_obj:
      self.response.write('Could not look up team info for %s' % id)
      return

    # Update DB
    team.twitter_id = json_obj[0].get('id', 0)
    team.put()

    msg = 'Updated %s with twitter id %d' % (id, team.twitter_id)
    logging.info(msg)
    self.response.write(msg)


app = webapp2.WSGIApplication([
  ('/teams/view', TeamListHandler),
  ('/teams/edit', TeamEditorHandler),
], debug=True)
