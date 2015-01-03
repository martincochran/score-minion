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
from google.appengine.ext import testbed

import show_tweets
import tweets
import web_test_base

class ShowTweetsTest(web_test_base.WebTestBase):
  def setUp(self):
    super(ShowTweetsTest, self).setUp()
    self.testapp = webtest.TestApp(show_tweets.app)

    self.CreateTweet(1, ('bob', 2)).put()

    # Create a tweet with integers
    twt = self.CreateTweet(4, ('alice', 3))
    twt.entities.integers = [tweets.IntegerEntity(), tweets.IntegerEntity()]
    twt.put()

  def tearDown(self):
    # Reset the URL stub to the original function
    self.testbed.deactivate()

  def testSanityGet(self):
    response = self.testapp.get('/show_tweets')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('alice') != -1)
    self.assertTrue(response.body.find('bob') == -1)

  def testShowAllGet(self):
    response = self.testapp.get('/show_tweets?all=y')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('bob') != -1)
    self.assertTrue(response.body.find('alice') != -1)

  def testDebugGet(self):
    response = self.testapp.get('/show_tweets?debug=y')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('alice') != -1)
    self.assertTrue(response.body.find('bob') == -1)

  def testNumTweetsGet(self):
    response = self.testapp.get('/show_tweets?num=20')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('alice') != -1)
    self.assertTrue(response.body.find('bob') == -1)

  def testNumTweetsGet_fewerThanTotal(self):
    response = self.testapp.get('/show_tweets?num=1&all=y')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('alice') != -1)
    self.assertTrue(response.body.find('bob') == -1)

  def testNumTweetsGet_badValue(self):
    response = self.testapp.get('/show_tweets?num=y')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('alice') != -1)
    self.assertTrue(response.body.find('bob') == -1)

  def testSpecifyUser_noResults(self):
    response = self.testapp.get('/show_tweets?user=bob')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('alice') == -1)
    self.assertTrue(response.body.find('bob') == -1)

  def testSpecifyUser_someResults(self):
    response = self.testapp.get('/show_tweets?user=bob&all=y')
    self.assertEqual(200, response.status_int)
    self.assertTrue(response.body.find('alice') == -1)
    self.assertTrue(response.body.find('bob') != -1)


if __name__ == '__main__':
  unittest.main()
