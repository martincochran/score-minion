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

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()

from google.appengine.ext.ndb.stats import GlobalStat

import webtest
from stats import app as stats_app
import web_test_base


class StatsHandlerTest(web_test_base.WebTestBase):
  def setUp(self):
    super(StatsHandlerTest, self).setUp()
    self.testapp = webtest.TestApp(stats_app)

  def testGetNoStats(self):
    """Tests correctly handling case where no stats are returned."""
    response = self.testapp.get('/stats')
    self.assertEqual(200, response.status_int)

  @mock.patch.object(GlobalStat, 'query')
  def testBasicStats(self, mock_global_stat):
    """Tests main case where some stats are returned."""
    fake_response = mock.MagicMock()
    fake_response.bytes = 5
    fake_response.count = 10
    mock_global_stat.return_value = fake_response
    response = self.testapp.get('/stats')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('5') != 1)
    self.assertTrue(response.body.find('10') != 1)
