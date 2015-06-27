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

import logging
import mock
import os
import unittest
import webtest

import test_env_setup

from google.appengine.api import users

import oauth_playground
import web_test_base


class OauthPlaygroundTest(web_test_base.WebTestBase):
  def setUp(self):
    super(OauthPlaygroundTest, self).setUp()
    self.testapp = webtest.TestApp(oauth_playground.app)

  @mock.patch.object(users, 'get_current_user')
  def testSanityGet(self, mock_get_current_user):
    """Ensure GET won't throw any exceptions."""
    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    response = self.testapp.get(oauth_playground.URL_BASE)
    self.assertEqual(200, response.status_int)

  @mock.patch.object(users, 'get_current_user')
  def testPost(self, mock_get_current_user):
    """Verify the twitter_client output is present."""
    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    twt = self.CreateTweet('5', ('bob', '132'))
    lookup_lists_response = '{"lists": [{"id_str": "1234"}]}'
    list_twt = self.CreateTweet('8', ('chuck', '12'))

    self.return_statuscode = [200, 200, 200]
    self.return_content = [twt.toJsonString(), lookup_lists_response,
                           list_twt.toJsonString()]

    params = {
      'account': 'test_account',
      'num': 2,
    }
    response = self.testapp.post(oauth_playground.URL_BASE, params)
    self.assertEqual(200, response.status_int)
    logging.info(response.body)
    
    # Ensure the responses show up in the response
    self.assertTrue(response.body.find(u'bob') != -1)
    self.assertTrue(response.body.find(u'1234') != -1)
    self.assertTrue(response.body.find(u'chuck') != -1)

  @mock.patch.object(users, 'get_current_user')
  def testPost_emptyResponses(self, mock_get_current_user):
    """Verify the twitter_client output is present."""
    mock_get_current_user.return_value = users.User(
        email='bob@test.com', _auth_domain='gmail.com')

    self.return_statuscode = [200, 200, 200]
    self.return_content = ['{}', '{}', '{}']

    params = {
      'account': 'test_account',
      'num': 2,
    }
    response = self.testapp.post(oauth_playground.URL_BASE, params)
    logging.info(response.body)
    self.assertEqual(200, response.status_int)


if __name__ == '__main__':
  unittest.main()
