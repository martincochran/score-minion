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


def QueryAndSetTweet(tweet):
  """Determine if this tweet is in the DB and put it if not.

  Args:
    tweet: json tweet object.
     
  Returns:
    The canonical datastore object for this tweet, or none if the argument
    was not a valid tweet json object.
  """
  if not tweet:
    logging.info('Empty tweet - exiting')
    return None

  # First look up to see if the tweet exists.
  tweet_query = tweets.Tweet.query(ancestor=tweets.tweet_key(tweet.id_str))
  twts = tweet_query.fetch(1)

  # TODO: if we care, update tweet with any new fields from this tweet
  if twts:
    return twts[0]

  # Looks like a new tweet - let's store it.
  tweet.put()
  return tweet
