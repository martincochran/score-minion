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
import json
import logging
import os

from google.appengine.api import users
from google.appengine.ext import ndb

import jinja2
import webapp2

import oauth_token_manager
import tweets
import twitter_fetcher


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class ShowTweetsHandler(webapp2.RequestHandler):
  def get(self):
    # TODO: figure out if there is a better way to do a structured property filter
    # TODO: perhaps store the name and screen_name in the tweet db for convenience
    tweet_query = tweets.Tweet.query().order(-tweets.Tweet.created_at)
    twts = tweet_query.fetch(200)

    # TODO: this line is not being tested when twts is empty
    twts = [twt for twt in twts if (twt.entities and len(twt.entities.integers) > 1)]

    template_values = {
      'tweets': twts,
    }

    template = JINJA_ENVIRONMENT.get_template('html/show_tweets.html')
    self.response.write(template.render(template_values))

app = webapp2.WSGIApplication([
  ('/show_tweets', ShowTweetsHandler),
  ('/show_tweets/', ShowTweetsHandler),
], debug=True)
