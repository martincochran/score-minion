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

import os

from google.appengine.api import users

import oauth_token_manager
import twitter_fetcher

import jinja2
import webapp2

URL_BASE = '/oauth/playground'


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

# The default account from which data will be queried.
SCREEN_NAME_DEFAULT = 'martin_cochran'


USER_ID_DEFAULT = '568757027'

# The default number of results from each fetch type. For simplicity, this
# value will passed as the 'count' param for every function in
# twitter_fetcher.TwitterFetcher which has 'count' as a keyword argument.
NUM_DEFAULT = '1'


class OauthPlaygroundHandler(webapp2.RequestHandler):
  def get(self):
    """Presents a form to specify which values should be queried.
    
    Each major method in twitter_fetcher.TwitterFetcher will be called.
    """
    template_values = self._PopulateTemplateValues()
    template = JINJA_ENVIRONMENT.get_template('html/oauth_playground.html')
    self.response.write(template.render(template_values))

  def post(self):
    """Makes the calls using TwitterFetcher with the given params."""
    template_values = self._PopulateTemplateValues()

    # Create the oauth client
    token_manager = oauth_token_manager.OauthTokenManager()
    fetcher = twitter_fetcher.TwitterFetcher(token_manager)

    # Do the requests
    try:
      template_values['user_timeline_response'] = fetcher.UserTimeline(
          template_values['account'], count=template_values['num'])
    except twitter_fetcher.FetchError as e:
      template_values['user_timeline_response'] = e
    try:
      template_values['lookup_lists_response'] = fetcher.LookupLists(
          template_values['account'], count=template_values['num'])
    except twitter_fetcher.FetchError as e:
      template_values['lookup_lists_response'] = e
    try:
      template_values['lookup_user_response'] = fetcher.LookupUsers(
          template_values['user_id'])
    except twitter_fetcher.FetchError as e:
      template_values['lookup_user_response'] = e

    # Find the first list and fetch tweets from it
    list_id = self._GetFirstListId(template_values['lookup_lists_response'])
    if list_id:
      try:
        template_values['list_statuses_response'] = fetcher.ListStatuses(
            list_id, count=template_values['num'])
      except twitter_fetcher.FetchError as e:
        template_values['list_statuses_response'] = e

    # Render the results
    template = JINJA_ENVIRONMENT.get_template('html/oauth_playground.html')
    self.response.write(template.render(template_values))

  def _PopulateTemplateValues(self):
    """Populate fetch params based on form values or defaults.
    
    Returns:
      A dictionary with all the required params to render the page without
      errors. If the user specified params in the POST request, these
      params will be returned with the specified values in the dictionary.
    """
    account = self.request.get('screen_name',
        default_value=SCREEN_NAME_DEFAULT)
    num = int(self.request.get('num', default_value=NUM_DEFAULT))
    user_id = self.request.get('user_id',
        default_value=USER_ID_DEFAULT)
    template_values = {
      'account': account,
      'num': num,
      'user_id': user_id,
      'user_timeline_response': '',
      'lookup_lists_response': '',
      'lookup_user_response': '',
      'list_statuses_response': '',
    }
    return template_values

  def _GetFirstListId(self, json_obj):
    """Returns the first list_id in the parsed response.
    
    Args:
      json_obj: parsed JSON response from
        twitter_fetcher.TwitterFetcher.LookupLists
    Returns:
      The first list ID (string) or an empty string if there is none.
    """
    if type(json_obj) == twitter_fetcher.FetchError:
      return ''
    lists = json_obj.get('lists', [])
    if lists:
      return lists[0].get('id_str', '')
    return ''


app = webapp2.WSGIApplication([
  (URL_BASE, OauthPlaygroundHandler),
  ('%s/' % URL_BASE, OauthPlaygroundHandler),
], debug=True)
