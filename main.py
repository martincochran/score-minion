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

from google.appengine.api import users

import webapp2

import oauth_token_manager
import twitter_fetcher

class MainHandler(webapp2.RequestHandler):
  def get(self):
    # Checks for active Google account session
    user = users.get_current_user()

    if user:
      self.response.headers['Content-Type'] = 'text/html'
      self.response.write('Hello, %s\n' % user.nickname())
      token_manager = oauth_token_manager.OauthTokenManager()
      fetcher = twitter_fetcher.TwitterFetcher(token_manager)
      self.response.write('Last tweet by martin_cochran: %s' % fetcher.LoadTimeline(
        'martin_cochran', count=20))
      self.response.write('\n<a href="%s">sign out</a>' % users.create_logout_url('/'))
    else:
      self.redirect(users.create_login_url(self.request.uri))

app = webapp2.WSGIApplication([('/', MainHandler)], debug=True)
