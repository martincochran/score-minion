#!/usr/bin/env python
#
# Copyright 2015 Martin Cochran
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
import unittest
import webtest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()
from google.appengine.ext import testbed

import endpoints
from endpoints import api_config

# Mock out the endpoints method
def null_decorator(*args, **kwargs):
    def decorator(method):
        def wrapper(*args, **kwargs):
            return method(*args, **kwargs)
        return wrapper
    return decorator

endpoints.method = null_decorator

# For some reason this is necessary before importing scores_api
# and using endpoints.
os.environ['CURRENT_VERSION_ID'] = '1.2'
import scores_api
import scores_messages
import web_test_base

class ScoresApiTest(web_test_base.WebTestBase):
  def setUp(self):
    super(ScoresApiTest, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.api = scores_api.ScoresApi()

    self.testapp = webtest.TestApp(scores_api.app)

  def testSanityGetGames(self):
    """Ensure no exceptions are thrown on simple requests to GetGames."""
    self.assertEqual(scores_messages.GamesResponse(),
        self.api.GetGames(scores_messages.GamesRequest()))

  def testSanityGetGameInfo(self):
    """Ensure no exceptions are thrown on simple requests to GetGameInfo."""
    self.assertEqual(scores_messages.GameInfoResponse(),
        self.api.GetGameInfo(scores_messages.GameInfoRequest()))


if __name__ == '__main__':
  unittest.main()
