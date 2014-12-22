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

from google.appengine.api import users
from google.appengine.ext import ndb

DEFAULT_SECRET_DB_NAME = 'twitter_secret_db'

def api_secret_key(secret_table_name=DEFAULT_SECRET_DB_NAME):
  """Constructs a Datastore key for an API secret secret_table_name."""
  return ndb.Key('ApiSecret', secret_table_name)

def token_key(token_table_name=DEFAULT_SECRET_DB_NAME):
  """Constructs a Datastore key for an Oauth token token_table_name."""
  return ndb.Key('OauthToken', token_table_name)

class ApiSecret(ndb.Model):
  """Models an individual Oauth secret or token entry."""
  author = ndb.UserProperty()
  content = ndb.StringProperty(indexed=False)
  date_added = ndb.DateTimeProperty(auto_now_add=True)

class OauthTokenManager:

  def __init__(self, is_mock=False):
    self.is_mock = is_mock
    self.mock_secret = ''
    self.mock_token = ''

  def GetSecret(self):
    if self.is_mock:
      return self.mock_secret

    account_query = ApiSecret.query(
      ancestor=api_secret_key()).order(-ApiSecret.date_added)
    oauth_secrets = account_query.fetch(1)
    if not oauth_secrets:
      return ''
    return oauth_secrets[0].content

  def GetToken(self):
    if self.is_mock:
      return self.mock_token

    account_query = ApiSecret.query(
      ancestor=token_key()).order(-ApiSecret.date_added)
    oauth_tokens = account_query.fetch(1)
    if not oauth_tokens:
      return ''
    return oauth_tokens[0].content

  def AddToken(self, token):
    if self.is_mock:
      self.mock_token = token
      return
    account = ApiSecret(parent=token_key())
    if users.get_current_user():
      account.author = users.get_current_user()
    account.content = token
    account.put()

  def AddSecret(self, secret):
    if self.is_mock:
      self.mock_secret = secret
      return
    account = ApiSecret(parent=api_secret_key())
    if users.get_current_user():
      account.author = users.get_current_user()
    account.content = secret
    account.put()

  def SetMockSecret(self, secret):
    self.mock_secret = secret

  def SetMockToken(self, token):
    self.mock_token = token
