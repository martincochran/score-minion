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

import os
import unittest

import webapp2
import webtest

from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_stub
from google.appengine.api import users
from google.appengine.ext import testbed

import api_admin
import tests

class ApiAdminTest(unittest.TestCase):
  def setUp(self):

    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_urlfetch_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_user_stub()
    self.url_fetch_stub = self.testbed.get_stub(testbed.URLFETCH_SERVICE_NAME)

    self.return_statuscode = [200]
    self.return_content = ['test response']

    # Stub out the call to fetch the URL
    def _FakeFetch(url, payload, method, headers, request, response,
        follow_redirects=True, deadline=urlfetch_stub._API_CALL_DEADLINE,
        validate_certificate=urlfetch_stub._API_CALL_VALIDATE_CERTIFICATE_DEFAULT):
      response.set_statuscode(self.return_statuscode.pop(0))
      response.set_content(self.return_content.pop(0))

    self.saved_retrieve_url = self.url_fetch_stub._RetrieveURL
    self.url_fetch_stub._RetrieveURL = _FakeFetch

    app = webapp2.WSGIApplication([('/api_admin', api_admin.ApiAdminHandler)])
    self.testapp = webtest.TestApp(app)

  def tearDown(self):
    # Reset the URL stub to the original function
    self.url_fetch_stub._RetrieveURL = self.saved_retrieve_url
    self.testbed.deactivate()

  def testSanityGet(self):
    def FakeGetCurrentUser():
      return users.User(email='bob@test.com', _auth_domain='gmail.com')

    self.saved_get_current_user = users.get_current_user
    users.get_current_user = FakeGetCurrentUser

    # Set the admin status of the user
    os.environ['USER_IS_ADMIN'] = '1'

    response = self.testapp.get('/api_admin')
    users.get_current_user = self.saved_get_current_user
    self.assertEqual(200, response.status_int)

  def testPutKey(self):
    app2 = webapp2.WSGIApplication([('/api_admin/put_key', api_admin.PutKeyHandler)])
    self.testapp2 = webtest.TestApp(app2)

    def FakeGetCurrentUser():
      return users.User(email='bob@test.com', _auth_domain='gmail.com')

    self.saved_get_current_user = users.get_current_user
    users.get_current_user = FakeGetCurrentUser

    # Set the admin status of the user
    os.environ['USER_IS_ADMIN'] = '1'

    params = {'content': 'new key'}
    response = self.testapp2.post('/api_admin/put_key', params)
    users.get_current_user = self.saved_get_current_user

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/api_admin')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('new key') != -1)


if __name__ == '__main__':
  unittest.main()
