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

import datetime
import logging
import os

from google.appengine.ext import ndb

import jinja2
import webapp2

import tweets


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class ShowTweetsHandler(webapp2.RequestHandler):
  def get(self):
    if self.request.get('all'):
      tweet_query = tweets.Tweet.query().order(-tweets.Tweet.created_at)
    else:
      tweet_query = tweets.Tweet.query(
          tweets.Tweet.two_or_more_integers == True).order(-tweets.Tweet.created_at)
    account = self.request.get('user')
    if account:
      if self.request.get('all'):
        tweet_query = tweets.Tweet.query(
            tweets.Tweet.author_screen_name == account).order(-tweets.Tweet.created_at)
      else:
        tweet_query = tweets.Tweet.query(ndb.AND(tweets.Tweet.two_or_more_integers == True,
            tweets.Tweet.author_screen_name == account)).order(-tweets.Tweet.created_at)

    num = 10
    try:
      num = int(self.request.get('num'))
    except ValueError:
      logging.warning('Could not parse num from %s', self.request.get('num'))

    num = min(num, 1000)
    num = max(num, 1)

    dbg = self.request.get('debug')
    logging.info('Fetching %s tweets', num)
    twts = tweet_query.fetch(num)

    dbg = self.request.get('debug')

    # Shift UTC dates to PST
    secs = 8 * 60 * 60
    dates = [d.created_at - datetime.timedelta(0, secs, 0) for d in twts]

    tweets_and_dates = zip(twts, dates)

    template_values = {
      'tweets_and_dates': tweets_and_dates,
      'debug': self.request.get('debug'),
    }

    template = JINJA_ENVIRONMENT.get_template('html/show_tweets.html')
    self.response.write(template.render(template_values))

app = webapp2.WSGIApplication([
  ('/show_tweets', ShowTweetsHandler),
], debug=True)
