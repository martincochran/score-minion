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

import logging
import os

from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.ext import ndb

import jinja2
import webapp2

import crawl_lists
import oauth_token_manager
import tweets
import twitter_fetcher


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class AccountsHandler(webapp2.RequestHandler):
  def get(self):

    account_query = tweets.User.query().order(tweets.User.screen_name)
    accounts = account_query.fetch()

    if not accounts:
      accounts = []

    if users.get_current_user():
      url = users.create_logout_url(self.request.uri)
      url_linktext = 'Logout'
    else:
      url = users.create_login_url(self.request.uri)
      url_linktext = 'Login'

    template_values = {
      'accounts': accounts,
      'num_accounts': len(accounts),
      'url_text': url_linktext,
      'url': url,
    }
 
    template = JINJA_ENVIRONMENT.get_template('html/accounts.html')
    self.response.write(template.render(template_values))


class AddAccountHandler(webapp2.RequestHandler):
  """Add a new Oauth secret to be used to fetch Twitter data."""
  def post(self):
    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)

    IndexAccountData(self.request.get('account'), 100, fetcher)
    self.redirect('/accounts')


def IndexAccountData(screen_name, num_tweets, fetcher):
  """Index the data associated with this account.

  Args:
    screen_name: The screen_name for the user
    num_tweets: The number of tweets to index
    fetcher: The twitter_fetcher.TwitterFetcher object used for fetching
  """
  try:
    json_obj = fetcher.UserTimeline(screen_name, count=num_tweets)
  except twitter_fetcher.FetchError as e:
    logging.warning('Could not load timeline for user %s', screen_name)
    return

  tweets.User.GetOrInsertFromJson(json_obj[0].get('user', {}))
  for json_twt in json_obj:
    tweets.Tweet.GetOrInsertFromJson(json_twt)


class DeleteAccountHandler(webapp2.RequestHandler):
  def post(self):
    logging.info('Deleting account: %s' % self.request.get('account'))
    account_query = tweets.User.query(
        tweets.User.screen_name == self.request.get('account'))
    for account in account_query:
      account.key.delete()
    self.redirect('/accounts')


class DeleteAllAccountsHandler(webapp2.RequestHandler):
  def post(self):
    account_query = tweets.User.query()
    for account in account_query:
      account.key.delete()
    self.redirect('/accounts')


class DeleteAllTweetsHandler(webapp2.RequestHandler):
  def post(self):
    tweet_query = tweets.Tweet.query()
    for tweet in tweet_query:
      tweet.key.delete()

    # TODO: consolidate the logic.  Perhaps just add a task to delete the
    # memcache entries and test it in that handler.  Avoiding cross-handler
    # dependencies would be good for testing purposes.
    admin_list_result = crawl_lists.ManagedLists.query(
        ancestor=crawl_lists.lists_key()).fetch(1)

    # For every list, enqueue a task to crawl that list.
    if admin_list_result:
      for l in admin_list_result[0].list_ids:
        memcache.delete(key=crawl_lists.LISTS_LATEST_KEY_PREFIX + l,
            namespace=crawl_lists.LISTS_LATEST_NAMESPACE)
    self.redirect('/accounts')


class RecrawlTweetsHandler(webapp2.RequestHandler):
  def post(self):
    accounts_to_recrawl = []
    account_query = tweets.User.query()
    for account in account_query:
      accounts_to_recrawl.append(account.screen_name)
      account.key.delete()
    tweet_query = tweets.Tweet.query()
    for tweet in tweet_query:
      tweet.key.delete()

    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)

    num_tweets = 10
    try:
      num_tweets = int(self.request.get('num_tweets'))
    except ValueError:
      logging.warning('Could not parse num_tweets from %s', self.request.get('num_tweets'))

    num_tweets = min(num_tweets, 1000)
    num_tweets = max(num_tweets, 1)

    logging.info('Recrawling with %s num_tweets', num_tweets)

    for account in accounts_to_recrawl:
      IndexAccountData(account, self.request.get('num_tweets'), fetcher)
    self.redirect('/accounts')


app = webapp2.WSGIApplication([
  ('/accounts', AccountsHandler),
  ('/accounts/', AccountsHandler),
  ('/accounts/follow_account', AddAccountHandler),
  ('/accounts/delete_account', DeleteAccountHandler),
  ('/accounts/delete_all_accounts', DeleteAllAccountsHandler),
  ('/accounts/delete_all_tweets', DeleteAllTweetsHandler),
  ('/accounts/recrawl', RecrawlTweetsHandler),
], debug=True)
