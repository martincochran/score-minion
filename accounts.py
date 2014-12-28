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

import json
import logging

from google.appengine.api import users
from google.appengine.ext import ndb

import webapp2

import oauth_token_manager
import tweets
import twitter_fetcher

MAIN_PAGE_FOOTER_TEMPLATE = """\
    <form action="/accounts/follow_account" method="post">
      <div><textarea name="account" rows="3" cols="60"></textarea></div>
      <div><input type="submit" value="Add account to follow"></div>
    </form>
    <hr>
    <a href="%s">%s</a>
  </body>
</html>
"""

class AccountsHandler(webapp2.RequestHandler):
  def get(self):
    self.response.write('<html><body>')

    account_query = tweets.User.query().order(-tweets.User.date_added)
    accounts = account_query.fetch(50)

    for user in accounts:
      self.response.write('<b>%s</b> added at %s' % (
            user.screen_name, user.date_added))
      self.response.write('<p>')

    if users.get_current_user():
      url = users.create_logout_url(self.request.uri)
      url_linktext = 'Logout'
    else:
      url = users.create_login_url(self.request.uri)
      url_linktext = 'Login'

    # Write the submission form and the footer of the page
    self.response.write(MAIN_PAGE_FOOTER_TEMPLATE % (url, url_linktext))

class AddAccountHandler(webapp2.RequestHandler):
  """Add a new Oauth secret to be used to fetch Twitter data."""
  def post(self):
    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)

    # TODO: fetch more tweets and add them all in the same transaction
    tweet = fetcher.LoadTimeline(self.request.get('account'), count=30)
    if tweet.status_code == 200:
      json_obj = json.loads(tweet.content)
      user = tweets.User.fromJson(json_obj[0].get('user', {}))
      if user:
        user.put()
      else:
        logging.info('Could not parse tweet for user %s', self.request.get('account'))
      for json_twt in json_obj:
        twt = tweets.Tweet.fromJson(json_twt)
        if twt:
          twt.put()
    else:
      logging.info('Could not load tweet for user %s', self.request.get('account'))

    self.redirect('/accounts')

app = webapp2.WSGIApplication([
  ('/accounts', AccountsHandler),
  ('/accounts/', AccountsHandler),
  ('/accounts/follow_account', AddAccountHandler),
], debug=True)
