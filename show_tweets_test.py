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

from google.appengine.api import users
from google.appengine.ext import testbed

import show_tweets
import tweets

class AccountsTest(unittest.TestCase):
  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_user_stub()

    app = webapp2.WSGIApplication([('/show_tweets', show_tweets.ShowTweetsHandler)])
    self.testapp = webtest.TestApp(app)

  def tearDown(self):
    # Reset the URL stub to the original function
    self.testbed.deactivate()

  @patch.object(users, 'get_current_user')
  def testSanityGet(self, mock_get_current_user):
    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    response = self.testapp.get('/show_tweets')
    self.assertEqual(200, response.status_int)


