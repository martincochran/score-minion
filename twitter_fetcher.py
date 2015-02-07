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


class FetchError(Exception):
  """Any error that occurred with the fetch."""
  pass

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
  STATUS_URL = '/statuses/user_timeline.json'
  FRIENDS_URL = '/friends/ids.json'
  FOLLOWERS_URL = '/friends/ids.json'
  SEARCH_URL = '/search/tweets.json'
  LOOKUP_USERS_URL = '/users/lookup.json'
  LIST_LISTS_URL = '/lists/ownerships.json'
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

    Args:
      screen_name: Screen name of the user to load the timeline for.
    Args:
      count: Number of elements from the timeline to load.

    Rate limit: 300 / 15 minute window
    More info: https://dev.twitter.com/rest/reference/get/statuses/user_timeline
    """
    url = '%s%s' % (self.API_BASE_URL, self.STATUS_URL)
    params = {
      'count': count,
      'screen_name': screen_name,
    }

    response = self._FetchResults(url, params=params)
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

  def LookupLists(self, screen_name, count=50):
    """List the lists owned by a given user.

    Rate limit: 15 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/lists/ownerships
    """
    url = '%s%s' % (self.API_BASE_URL, self.LIST_LISTS_URL)
    params = {
      'count': count,
      'screen_name': screen_name,
    }

    response = self._FetchResults(url, params=params)
    return response

  def ListStatuses(self, list_id, count=200, include_rts=0, since_id=None,
      max_id=None):
    """Returns a timeline of tweets authored by members of the given list.

    Rate limit: 180 / 15 minute window.
    More info: https://dev.twitter.com/rest/reference/get/lists/statuses
    See also: https://dev.twitter.com/rest/public/timelines

    Args:
      list_id: The ID of the list
      count: num statuses to return
      include_rts: If 1, include retweets as well
      since_id: (optional) If supplied, fetch only tweets more recent than that
        id.
      max_id: (optional) If supplied, fetch only tweets older than that id.
    Returns:
      The response of the API call
    """
    url = '%s%s' % (self.API_BASE_URL, self.LIST_STATUSES_URL)
    params = {
      'count': count,
      'list_id': list_id,
      'include_rts': include_rts,
    }
    if since_id:
      params['since_id'] = since_id
    if max_id:
      params['max_id'] = max_id

    response = self._FetchResults(url, params=params)
    return response

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

  def _FetchResults(self, url, params={}):
    """Tries to fetch and return the parsed json results from the API.

    On a successful invocation the parsed, non-empty json object will be
    returned. On any error, including a non-200 status code in the response,
    a FetchError will be thrown.

    Args:
      url: (string) URL to fetch
      params: Dictionary of parameter to add to get requests
    Returns:
      The parsed json from the content of the response to the Http.request() method.
    Throws:
      FetchError on any underlying error or a non-200 status code response.
    """
    logging.info('Loading results from URL %s, %s', url, params)

    param_str = '&'.join(['%s=%s' % (i[0], i[1]) for i in params.iteritems()])
    if param_str:
      url = '%s?%s' % (url, param_str)

    try:
      response = urlfetch.fetch(url, headers=self._BuildHeaders())

      # Check to see if we need to re-authenticate to get a new token.
      if self._ShouldReAuthenticate(response):
        self._ReAuthenticate()
        # Try again, once.
        response = urlfetch.fetch(url, headers=self._BuildHeaders())
    except urlfetch.Error as e:
      logging.warning('Could not fetch URL %s: %s', url, e)
      raise FetchError(e)

    if response.status_code != 200:
      raise FetchError('Response code not 200: %s, %s' % (response.status_code,
          response.content))

    try:
      json_obj = json.loads(response.content)
    except ValueError as e:
      raise FetchError('Could not parse json response: %s' % response.content, e)

    if not json_obj:
      raise FetchError('Empty json response: %s' % response)

    return json_obj

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

    if type(errors) != list:
      return True
    if type(errors[0]) != dict:
      return True
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
