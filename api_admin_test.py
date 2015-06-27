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
import os
import unittest
import webtest

import test_env_setup

from google.appengine.api import users

import api_admin
import web_test_base


class ApiAdminTest(web_test_base.WebTestBase):
  def setUp(self):
    super(ApiAdminTest, self).setUp()
    self.SetJsonResponse('test response')
    self.testapp = webtest.TestApp(api_admin.app)

  @mock.patch.object(users, 'get_current_user')
  def testSanityGet(self, mock_get_current_user):
    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    response = self.testapp.get(api_admin.URL_BASE)
    self.assertEqual(200, response.status_int)

  @mock.patch.object(users, 'get_current_user')
  def testPutKey(self, mock_get_current_user):
    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    # TODO: any way to get this URL from the page itself?
    params = {'content': 'new key'}
    response = self.testapp.post('%s/put_key' % api_admin.URL_BASE, params)

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get(api_admin.URL_BASE)
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('new key') != -1)


if __name__ == '__main__':
  unittest.main()
