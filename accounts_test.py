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

import mock
from mock import patch

import os
import unittest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()

import webapp2
import webtest

from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_stub
from google.appengine.api import users
from google.appengine.ext import testbed

import accounts
import tweets

class AccountsTest(unittest.TestCase):
  def setUp(self):

    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_urlfetch_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_user_stub()
    self.url_fetch_stub = self.testbed.get_stub(testbed.URLFETCH_SERVICE_NAME)

    self.return_statuscode = [200]
    self.return_content = ['[{"user": {"id_str": "1234", "screen_name": "bob"}}]']

    # Stub out the call to fetch the URL
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      response.set_statuscode(self.return_statuscode.pop(0))
      response.set_content(self.return_content.pop(0))

    self.saved_retrieve_url = self.url_fetch_stub._RetrieveURL
    self.url_fetch_stub._RetrieveURL = _FakeFetch

    app = webapp2.WSGIApplication([('/accounts', accounts.AccountsHandler)])
    self.testapp = webtest.TestApp(app)

  def tearDown(self):
    # Reset the URL stub to the original function
    self.url_fetch_stub._RetrieveURL = self.saved_retrieve_url
    self.testbed.deactivate()

  @patch.object(users, 'get_current_user')
  def testSanityGet(self, mock_get_current_user):
    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

  @patch.object(users, 'get_current_user')
  def testFollowAccount(self, mock_get_current_user):
    app2 = webapp2.WSGIApplication([('/accounts/follow_account',
          accounts.AddAccountHandler)])
    self.testapp2 = webtest.TestApp(app2)

    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    params = {'account': 'bob'}
    response = self.testapp2.post('/accounts/follow_account', params)

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') != -1)


