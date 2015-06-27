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

from google.appengine.ext import testbed

import oauth_token_manager

class OauthTokenManagerTest(unittest.TestCase):
  def setUp(self):
    """Stub out the datastore so we can test it."""
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_memcache_stub()
    self.testbed.init_datastore_v3_stub()

  def tearDown(self):
    self.testbed.deactivate()

  def testMockManager(self):
    token_manager = oauth_token_manager.OauthTokenManager(is_mock=True)

    self.assertEquals('', token_manager.GetSecret())
    self.assertEquals('', token_manager.GetToken())

    secret = 'my secret'
    token = 'token for my secret'

    token_manager.AddSecret(secret)
    token_manager.AddToken(token)
    self.assertEquals(secret, token_manager.GetSecret())
    self.assertEquals(token, token_manager.GetToken())

    secret = 'new secret'
    token = 'token for new secret'

    token_manager.AddSecret(secret)
    token_manager.AddToken(token)
    self.assertEquals(secret, token_manager.GetSecret())
    self.assertEquals(token, token_manager.GetToken())

    # Ensure we didn't actually touch the data store.
    account_query = oauth_token_manager.ApiSecret.query(
      ancestor=oauth_token_manager.api_secret_key()).order(
      -oauth_token_manager.ApiSecret.date_added)
    oauth_secrets = account_query.fetch(10)
    self.assertEquals(0, len(oauth_secrets))

  def testDatastoreBackedManager(self):
    token_manager = oauth_token_manager.OauthTokenManager()

    self.assertEquals('', token_manager.GetSecret())
    self.assertEquals('', token_manager.GetToken())

    secret = 'my secret'
    token = 'token for my secret'

    token_manager.AddSecret(secret)
    token_manager.AddToken(token)
    self.assertEquals(secret, token_manager.GetSecret())
    self.assertEquals(token, token_manager.GetToken())

    secret = 'new secret'
    token = 'token for new secret'
    token_manager.AddSecret(secret)
    token_manager.AddToken(token)
    self.assertEquals(secret, token_manager.GetSecret())
    self.assertEquals(token, token_manager.GetToken())


if __name__ == '__main__':
  unittest.main()
