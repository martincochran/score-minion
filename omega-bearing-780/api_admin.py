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

from google.appengine.api import users

import oauth_token_manager

import webapp2

MAIN_PAGE_FOOTER_TEMPLATE = """\
    <form action="/api_admin/put_key" method="post">
      <div><textarea name="content" rows="3" cols="60"></textarea></div>
      <div><input type="submit" value="Input OAuth key"></div>
    </form>
    <hr>
    <a href="%s">%s</a>
  </body>
</html>
"""

class ApiAdminHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write('<html><body>')

    account_query = oauth_token_manager.ApiSecret.query(
      ancestor=oauth_token_manager.api_secret_key()).order(
      -oauth_token_manager.ApiSecret.date_added)
    accounts = account_query.fetch(10)

    for account in accounts:
      if account.author:
        self.response.write('<b>%s</b> wrote: at %s' % (
              account.author.nickname(), account.date_added))
      else:
        self.response.write('An anonymous person wrote:')
      self.response.write('<blockquote>%s</blockquote>' %
          cgi.escape(account.content))

    if users.get_current_user():
      url = users.create_logout_url(self.request.uri)
      url_linktext = 'Logout'
    else:
      url = users.create_login_url(self.request.uri)
      url_linktext = 'Login'

    # Write the submission form and the footer of the page
    self.response.write(MAIN_PAGE_FOOTER_TEMPLATE % (url, url_linktext))

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
