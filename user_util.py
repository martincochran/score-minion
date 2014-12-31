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

import logging

import tweets


def QueryAndSetUser(user):
  """Determine if this user is in the DB and put it if not.

  Args:
    user: json user object.
     
  Returns:
    The canonical datastore object for this user, or none if the argument
    was not a valid user json object.
  """
  if not user:
    logging.info('Empty user - exiting')
    return None

  # First look up to see if the user exists.
  account_query = tweets.User.query(ancestor=tweets.user_key(user.id_str))
  accounts = account_query.fetch(1)

  # TODO: if we care, update user with any new fields from this user
  if accounts:
    return accounts[0]

  # Looks like a new user - let's store it.
  user.put()
  return user
