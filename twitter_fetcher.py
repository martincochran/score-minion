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
  """Interface with the Twitter API using the 'Application Only' API.

  This allows the following functionality:
  - Pull user timelines
  - Access friends and followers of any account
  - Access lists resources
  - Search tweets
  - Retrieve any user information:
    - Lookup users
    - Show users (info similar to that which you get from viewing a user in Twitter app)
    - User search
    - Get contributors / contributees
  
  More info: https://dev.twitter.com/oauth/application-only
  Rate limits: https://dev.twitter.com/rest/public/rate-limits
  """

  TOKEN_URL = 'https://api.twitter.com/oauth2/token'

  API_BASE_URL = 'https://api.twitter.com/1.1'

  # TODO: change the parameter to user ids, which is stable
  STATUS_URL_TMPL = '/statuses/user_timeline.json?count=%s&screen_name=%s'
  FRIENDS_URL_TMPL = '/friends/ids.json?count=%s&screen_name=%s'
  FOLLOWERS_URL_TMPL = '/friends/ids.json?count=%s&screen_name=%s'
  SEARCH_URL = '/search/tweets.json'
  LOOKUP_USERS_URL = '/users/lookup.json'
  LIST_LISTS_URL = '/lists/list.json'
  LIST_STATUSES_URL = '/lists/statuses.json'
  LIST_MEMBERSHIPS_URL ='/lists/memberships.json'
  LIST_MEMBERS_URL ='/lists/members.json'
  LIST_SUBSCRIBERS_URL ='/lists/subscribers.json'
  LIST_SUBSCRIPTIONS_URL ='/lists/subscriptions.json'

  def __init__(self, token_manager):
    self.token_manager = token_manager
    self.secret_string = token_manager.GetSecret()
    self.bearer_token = token_manager.GetToken()

  def LoadTimeline(self, screen_name, count=1):
    """Fetches the last count posts from the timeline of screen_name.

    Rate limit: 300 / 15 minute window
    More info: https://dev.twitter.com/rest/reference/get/statuses/user_timeline
    """
    url = '%s%s' % (self.API_BASE_URL, self.STATUS_URL_TMPL % (count, screen_name))
    logging.info('Loading last %s posts from timeline for %s', count, screen_name)
    response = self._FetchResults(url)
    return response

  def Search(self):
    """Performs a search.

    Rate limit: 450 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/search/tweets
    """
    pass

  def Friends(self):
    """Fetches the friends for a given user.

    Rate limit: 15 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/friends/ids
    """
    pass

  def Followers(self):
    """Fetches the followers for a given user.

    Rate limit: 15 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/followers/ids
    """
    pass

  def LookupUsers(self):
    """Lookup the info for a set of users.

    Rate limit: 60 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/users/lookup
    """
    pass

  def LookupLists(self):
    """List the lists for a given user.

    Rate limit: 15 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/lists/list
    """
    pass

  def ListStatuses(self):
    """Returns a timeline of tweets authored by members of the given list.

    Rate limit: 180 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/lists/statuses
    """
    pass

  def ListMemberships(self):
    """Returns the lists the specified user has been added to.

    Rate limit: 15 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/lists/memberships
    """
    pass

  def ListMembers(self):
    """Returns the members of the specified list.

    Rate limit: 15 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/lists/members
    """
    pass

  def ListSubscribers(self):
    """Returns the subscribers of the specified list.

    Rate limit: 15 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/lists/subscribers
    """
    pass

  def ListSubscriptions(self):
    """Returns lists a user is subscribed to.

    Rate limit: 15 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/lists/subscriptions
    """
    pass

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
    logging.debug('Checking to see if we should re-authenticate: %s', response.status_code)
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

    # TODO: check on the type of errors[0]?
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
