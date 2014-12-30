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
from google.appengine.api import memcache
from google.appengine.ext import ndb

import webapp2

import crawl_lists
import oauth_token_manager
import tweets
import twitter_fetcher

MAIN_PAGE_FOOTER_TEMPLATE = """\
    <form action="/accounts/follow_account" method="post">
      <div><textarea name="account" rows="3" cols="60"></textarea></div>
      <div><input type="submit" value="Add account to follow"></div>
    </form>
    <form action="/accounts/delete_account" method="post">
      <div><textarea name="account" rows="3" cols="60"></textarea></div>
      <div><input type="submit" value="Name account to delete"></div>
    </form>
    <form action="/accounts/delete_all_accounts" method="post">
      <div><input type="submit" value="Delete all accounts"></div>
    </form>
    <form action="/accounts/delete_all_tweets" method="post">
      <div><input type="submit" value="Delete all tweets"></div>
    </form>
    <form action="/accounts/recrawl" method="post">
      <div><textarea name="num_tweets" rows="3" cols="60">100</textarea></div>
      <div><input type="submit" value="Recrawl tweets and users per team (also drops current db)"></div>
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

    IndexAccountData(self.request.get('account'), 100, fetcher)
    self.redirect('/accounts')


def IndexAccountData(screen_name, num_tweets, fetcher):
  """Index the data associated with this account.

  Args:
    screen_name: The screen_name for the user
    num_tweets: The number of tweets to index
    fetcher: The twitter_fetcher.TwitterFetcher object used for fetching
  """
  tweet = fetcher.LoadTimeline(screen_name, count=num_tweets)
  if tweet.status_code != 200:
    logging.info('Could not load tweet for user %s', screen_name)
    return

  json_obj = json.loads(tweet.content)
  user = tweets.User.fromJson(json_obj[0].get('user', {}))
  if user:
    # Account clean-up:
    # First look up to see if there are any other account objects and delete them.
    account_query = tweets.User.query(tweets.User.id_str == user.id_str)
    for account in account_query:
      account.key.delete()
    user.put()
  else:
    logging.info('Could not parse tweet for user %s', screen_name)
  parsed_tweets = []
  for json_twt in json_obj:
    twt = tweets.Tweet.fromJson(json_twt)
    if twt:
      parsed_tweets.append(twt)
    else:
      logging.warning('Could not parse tweet from %s', json_twt)
  for tweet in parsed_tweets:
    logging.info('Adding tweet %s', tweet)
    tweet.put()


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
