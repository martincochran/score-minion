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
import os
import unittest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()

from google.appengine.ext import testbed

import user_util
import tweets

class UserUtilTest(unittest.TestCase):
  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_user_stub()

  def tearDown(self):
    # Reset the URL stub to the original function
    self.testbed.deactivate()

  def testQueryAndSetTweet(self):
    user = tweets.User.fromJson(json.loads(
        '{"id_str": "2", "screen_name": "bob"}'))

    user_query = tweets.User.query(ancestor=tweets.user_key(user.id_str))
    users = user_query.fetch(1)
    self.assertFalse(users)

    user_util.QueryAndSetUser(user)
    user_query = tweets.User.query(ancestor=tweets.user_key(user.id_str))
    users = user_query.fetch(1)
    self.assertEqual(1, len(users))
    self.assertEqual(users[0], user)

    # This will be a different object since the creation date will be different
    new_user = tweets.User.fromJson(json.loads(
        '{"id_str": "2", "screen_name": "bob"}'))

    returned_user = user_util.QueryAndSetUser(new_user)

    self.assertEqual(returned_user, user)
    self.assertFalse(user == new_user)
    self.assertFalse(returned_user == new_user)
 
    user_query = tweets.User.query(ancestor=tweets.user_key(user.id_str))
    users = user_query.fetch(1)
    self.assertEqual(1, len(users))
    self.assertEqual(users[0], user)
