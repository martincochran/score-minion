#!/usr/bin/env python
#
# Copyright 2014 Martin Cochran
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

import cgi
import logging
import os

from google.appengine.api import users

import oauth_token_manager

import jinja2
import webapp2


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class ApiAdminHandler(webapp2.RequestHandler):
  def get(self):
    account_query = oauth_token_manager.ApiSecret.query(
      ancestor=oauth_token_manager.api_secret_key()).order(
      -oauth_token_manager.ApiSecret.date_added)
    accounts = account_query.fetch(10)

    logging.info('Loaded %s secrets', len(accounts))

    if users.get_current_user():
      url = users.create_logout_url(self.request.uri)
      url_linktext = 'Logout'
    else:
      url = users.create_login_url(self.request.uri)
      url_linktext = 'Login'

    template_values = {
      'accounts': accounts,
      'url_text': url_linktext,
      'url': url,
    }

    template = JINJA_ENVIRONMENT.get_template('html/api_admin.html')
    self.response.write(template.render(template_values))

class PutKeyHandler(webapp2.RequestHandler):
  """Add a new Oauth secret to be used to fetch Twitter data."""
  def post(self):
    token_manager = oauth_token_manager.OauthTokenManager()
    token_manager.AddSecret(self.request.get('content'))

    self.redirect('/api_admin')

app = webapp2.WSGIApplication([
  ('/api_admin', ApiAdminHandler),
  ('/api_admin/', ApiAdminHandler),
  ('/api_admin/put_key', PutKeyHandler),
], debug=True)
