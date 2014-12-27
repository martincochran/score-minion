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

import unittest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()

from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_service_pb
from google.appengine.api import urlfetch_stub
from google.appengine.ext import testbed
from google.appengine.runtime import apiproxy_errors

import oauth_token_manager
import twitter_fetcher

class TwitterFetcherTest(unittest.TestCase):

  def setUp(self):
    """Mock out the logic from urlfetch which does the actual fetching."""
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_urlfetch_stub()
    self.url_fetch_stub = self.testbed.get_stub(testbed.URLFETCH_SERVICE_NAME)

    self.return_statuscode = [500]
    self.return_content = ['']

    # Stub out the call to fetch the URL
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      response.set_statuscode(self.return_statuscode.pop(0))
      response.set_content(self.return_content.pop(0))

    self.saved_retrieve_url = self.url_fetch_stub._RetrieveURL
    self.token_manager = oauth_token_manager.OauthTokenManager(is_mock=True)

    # To make the calls to the real twitter API, do the following 3 things:
    # 1. Comment out this next line.
    self.url_fetch_stub._RetrieveURL = _FakeFetch

    # 2. Change this value to be a real Oauth bearer token -- OR --
    self.token_manager.AddToken('mock token')

    # 3. Change this value to be a real Oauth secret.
    self.token_manager.AddSecret('mock secret')

    self.fetcher = twitter_fetcher.TwitterFetcher(self.token_manager)

  def tearDown(self):
    # Reset the URL stub to the original function
    self.url_fetch_stub._RetrieveURL = self.saved_retrieve_url
    self.testbed.deactivate()
 
  def testLoadTimeline(self):
    """Test basic LoadTimeline functionality."""
    self.return_statuscode = [200]

    # Some common fields in the response content
    content_items = [
        '"id_str":"542785926674399232"',
        '"text":"I took @TheAtlantic\'s test. http:\/\/t.co\/ub2EMDIssE"',
        '"in_reply_to_status_id":null',
        '"in_reply_to_status_id_str":null',
        '"in_reply_to_user_id":null',
        '"in_reply_to_user_id_str":null',
    ]
    self.return_content = ['[%s]' % ','.join(content_items)]

    timeline = self.fetcher.LoadTimeline('martin_cochran')
    self.assertEquals(200, timeline.status_code)

  def testLoadTimeline_badMemberId(self):
    """Verify that getting a 404 reponse is handled correctly."""
    self.return_statuscode = [404]
    self.return_content = ['{"errors":[{"message":"Sorry, that page does not exist","code":34}]}']
    timeline = self.fetcher.LoadTimeline('bad_twitter_member_id')
    self.assertEquals(404, timeline.status_code)

  def testLoadTimeline_badlyFormattedRequest(self):
    """Verify that getting a 400 reponse is handled correctly."""
    self.return_statuscode = [400]
    self.return_content = ['']

    timeline = self.fetcher.LoadTimeline('%s')
    self.assertEquals(400, timeline.status_code)

  def testVerifyReauthenicatedCalledOnError(self):
    """Verify that needing to refresh token is handled correctly."""
    self.fetcher.bearer_token = 'bad token'

    self.return_statuscode = [401, 200, 200]
    self.return_content = [
        '{"errors":[{"message":"Invalid or expired token","code":89}]}',
        '{"token_type":"bearer","access_token":"new access token"}',
        '',
    ]
    timeline = self.fetcher.LoadTimeline('martin_cochran')
    self.assertEquals(200, timeline.status_code)

  def testReAuthenticate(self):
    self.return_statuscode = [200, 200]
    self.return_content = [
        '{"token_type":"bearer","access_token":"new access token"}',
        '',
    ]

    self.fetcher._ReAuthenticate()
    timeline = self.fetcher.LoadTimeline('martin_cochran')
    self.assertEquals(200, timeline.status_code)

  def testHandleTooManyRedirects(self):
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      raise apiproxy_errors.ApplicationError(
          urlfetch_service_pb.URLFetchServiceError.TOO_MANY_REDIRECTS)

    self.url_fetch_stub._RetrieveURL = _FakeFetch
    # TODO: handle this in the class?
    try:
      timeline = self.fetcher.LoadTimeline('martin_cochran')
      self.fail('Should have thrown an error')
    except urlfetch.TooManyRedirectsError as e:
      # Expected
      pass

  def testHandleInvalidUrlError(self):
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      raise apiproxy_errors.ApplicationError(
          urlfetch_service_pb.URLFetchServiceError.INVALID_URL)

    self.url_fetch_stub._RetrieveURL = _FakeFetch

    # TODO: handle this in the class?
    try:
      timeline = self.fetcher.LoadTimeline('martin_cochran')
      self.fail('Should have thrown an error')
    except urlfetch.InvalidURLError as e:
      # Expected
      pass

  def testHandleTimeout(self):
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      raise apiproxy_errors.ApplicationError(
          urlfetch_service_pb.URLFetchServiceError.DEADLINE_EXCEEDED)

    self.url_fetch_stub._RetrieveURL = _FakeFetch

    # TODO: handle this in the class?
    try:
      timeline = self.fetcher.LoadTimeline('martin_cochran')
      self.fail('Should have thrown an error')
    except urlfetch.DownloadError as e:
      # Expected
      pass

  def testHandleResponseTooLarge(self):
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      raise apiproxy_errors.ApplicationError(
          urlfetch_service_pb.URLFetchServiceError.RESPONSE_TOO_LARGE)

    self.url_fetch_stub._RetrieveURL = _FakeFetch

    # TODO: handle this in the class?
    try:
      timeline = self.fetcher.LoadTimeline('martin_cochran')
      self.fail('Should have thrown an error')
    except urlfetch.ResponseTooLargeError as e:
      # Expected
      pass

  def testHandleFetchError(self):
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      raise apiproxy_errors.ApplicationError(
          urlfetch_service_pb.URLFetchServiceError.FETCH_ERROR)

    self.url_fetch_stub._RetrieveURL = _FakeFetch

    # TODO: handle this in the class?
    try:
      timeline = self.fetcher.LoadTimeline('martin_cochran')
      self.fail('Should have thrown an error')
    except urlfetch.DownloadError as e:
      # Expected
      pass

  def testHandleUnspecifiedError(self):
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      raise apiproxy_errors.ApplicationError(
          urlfetch_service_pb.URLFetchServiceError.UNSPECIFIED_ERROR)

    self.url_fetch_stub._RetrieveURL = _FakeFetch

    # TODO: handle this in the class?
    try:
      timeline = self.fetcher.LoadTimeline('martin_cochran')
      self.fail('Should have thrown an error')
    except urlfetch.DownloadError as e:
      # Expected
      pass


if __name__ == '__main__':
  unittest.main()
