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

from google.appengine.api import urlfetch

class TwitterFetcher:
  """Interface with the Twitter API."""

  TOKEN_URL = 'https://api.twitter.com/oauth2/token'

  API_BASE_URL = 'https://api.twitter.com/1.1'
  STATUS_URL_TMPL = '/statuses/user_timeline.json?count=%s&screen_name=%s'

  def __init__(self, token_manager):
    self.token_manager = token_manager
    self.secret_string = token_manager.GetSecret()
    self.bearer_token = token_manager.GetToken()

  def LoadTimeline(self, screen_name, count=1):
    """Fetches the last count posts from the timeline of screen_name."""
    url = '%s%s' % (self.API_BASE_URL, self.STATUS_URL_TMPL % (count, screen_name))
    logging.info('Loading last %s posts from timeline for %s', count, screen_name)
    response = self._FetchResults(url)
    return response

  def _FetchResults(self, url):
    """Try to fetch the results from the API.

    Args:
      url: (string) URL to fetch
    Returns:
      The response object from the Http.request() method.
    """
    headers = self._BuildHeaders()
    response = urlfetch.fetch(url, headers=self._BuildHeaders())

    # Check to see if we need to re-authenticate to get a new token.
    if self._ShouldReAuthenticate(response):
      self._ReAuthenticate()
      # Try again, once.
      response = urlfetch.fetch(url, headers=self._BuildHeaders())

    return response

  def _BuildHeaders(self):
    return {'Authorization': 'Bearer %s' % self.bearer_token}

  def _ShouldReAuthenticate(self, response):
    """Determines if a re-authentication is necessary given an API response."""
    logging.info('Checking to see if we should re-authenticate: %s', response.status_code)
    if response.status_code not in [400, 401]:
      return False

    parsed_content = ''
    try:
      parsed_content = json.loads(response.content)
    except ValueError as e:
      logging.warning('Could not parse error code from response: %s, %s', response.content, e)
      return False
    errors = parsed_content.get('errors', [])
    if not errors:
      return False

    # check on the type of errors[0]?
    error_code = errors[0].get('code', -1)
    return int(error_code) in [89, 215]

  def _ReAuthenticate(self):
    """Obtain a new bearer token using the stored client secret.

    Submit a request to get a new token, parse the resulting json and get the
    'bearer' token as described in
    https://dev.twitter.com/oauth/application-only
    """
    headers = {
      'Authorization': 'Basic %s' % self.secret_string,
      'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
    }

    content = 'grant_type=client_credentials'

    logging.info('Obtaining new authentication code')
    response = urlfetch.fetch(self.TOKEN_URL, method='POST', payload=content,
        headers=headers)

    token_response = json.loads(response.content)
    self.bearer_token = token_response.get('access_token', '')
    if self.bearer_token:
      logging.info('Successfully updated bearer_token')

      # TODO: Sleep for a random amount of time, then check to see if token has
      # changed before writing.
      self.token_manager.AddToken(self.bearer_token)
    return self.bearer_token
