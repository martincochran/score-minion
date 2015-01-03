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
import webtest

import test_env_setup

# Must be done before importing any AE libraries
test_env_setup.SetUpAppEngineSysPath()

import accounts
import tweets
import web_test_base

class AccountsTest(web_test_base.WebTestBase):
  def setUp(self):
    super(AccountsTest, self).setUp()
    self.testapp = webtest.TestApp(accounts.app)

  def testSanityGet(self):
    self.assertEqual(200, self.testapp.get('/accounts').status_int)

  def testFollowAccount(self):
    response = self.testapp.post('/accounts/follow_account', {'account': 'bob'})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') != -1)

  def testDeleteAccount(self):
    params = {'account': 'bob'}
    # First add an account
    self.testapp.post('/accounts/follow_account', params)

    # Now delete it
    response = self.testapp.post('/accounts/delete_account', params)

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') == -1)

  def testDeleteAllAccounts(self):
    self.return_statuscode = [200, 200]
    self.return_content = [
        '[{"user": {"id_str": "1234", "screen_name": "bob"}}]',
        '[{"user": {"id_str": "9999", "screen_name": "steve"}}]',
    ]

    self.testapp.post('/accounts/follow_account', {'account': 'bob'})
    self.testapp.post('/accounts/follow_account', {'account': 'steve'})
    response = self.testapp.post('/accounts/delete_all_accounts', {})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') == -1)
    self.assertTrue(response.body.find('steve') == -1)

  def testDeleteAllAccounts(self):
    self.return_statuscode = [200, 200]
    self.return_content = [
        '[{"user": {"id_str": "1234", "screen_name": "bob"}}]',
        '[{"user": {"id_str": "9999", "screen_name": "steve"}}]',
    ]

    self.testapp.post('/accounts/follow_account', {'account': 'bob'})
    self.testapp.post('/accounts/follow_account', {'account': 'steve'})
    response = self.testapp.post('/accounts/delete_all_accounts', {})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # Verify the new key is in the body
    self.assertTrue(response.body.find('bob') == -1)
    self.assertTrue(response.body.find('steve') == -1)

  def testDeleteAllTweets(self):
    self.SetTimelineResponse(self.CreateTweet(123, ('bob', 1234)))

    # First add an account
    self.testapp.post('/accounts/follow_account', {'account': 'bob'})

    # Ensure there is at least one tweet in the db
    self.assertTweetDbContents(['123'])
    self.assertUserDbContents(['1234'])

    # Now delete it
    response = self.testapp.post('/accounts/delete_all_tweets', {})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)
    self.assertTweetDbContents([])
    self.assertUserDbContents(['1234'])

    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # The account is still there, though
    self.assertTrue(response.body.find('bob') != -1)

  def testRecrawl(self):
    self.return_statuscode = [200, 200, 200, 200]
    self.return_content = [
        '[{"user": {"id_str": "1234", "screen_name": "bob"}, "id_str": "123"}]',
        '[{"user": {"id_str": "999", "screen_name": "steve"}, "id_str": "456"}]',
        '[{"user": {"id_str": "1234", "screen_name": "bob"}, "id_str": "777"}]',
        '[{"user": {"id_str": "999", "screen_name": "steve"}, "id_str": "888"}]',
    ]

    # First add an account
    self.testapp.post('/accounts/follow_account', {'account': 'bob'})
    self.testapp.post('/accounts/follow_account', {'account': 'steve'})

    self.assertTweetDbContents(['123', '456'])
    self.assertUserDbContents(['1234', '999'])

    # Now delete it
    response = self.testapp.post('/accounts/recrawl', {})

    # This re-directs back to the main handler.
    self.assertEqual(302, response.status_int)

    self.assertTweetDbContents(['777', '888'])
    self.assertUserDbContents(['1234', '999'])

    response = self.testapp.get('/accounts')
    self.assertEqual(200, response.status_int)

    # The account is still there, though
    self.assertTrue(response.body.find('bob') != -1)
    self.assertTrue(response.body.find('steve') != -1)


if __name__ == '__main__':
  unittest.main()
