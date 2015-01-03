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
import unittest
import webtest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()
from google.appengine.api import users

import main
import web_test_base


class MainTest(web_test_base.WebTestBase):
  def setUp(self):
    super(MainTest, self).setUp()
    self.testapp = webtest.TestApp(main.app)
    self.SetJsonResponse('{"text": "test response"}')

  def testGetNotLoggedIn(self):
    response = self.testapp.get('/')

    self.assertEqual(302, response.status_int)

  @mock.patch.object(users, 'get_current_user')
  def testGetLoggedIn(self, mock_get_current_user):
    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    response = self.testapp.get('/')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('test response') != -1)


if __name__ == '__main__':
  unittest.main()
