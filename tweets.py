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

import datetime
import logging
import os
import re

from google.appengine.api import users
from google.appengine.ext import ndb

DEFAULT_TWEET_DB_NAME = 'tweet_db'
DEFAULT_AUTHOR_DB_NAME = 'author_db'

DATE_PARSE_FMT_STR = '%a %b %d %H:%M:%S %Y'

# On App Engine prod this will be set correctly, but in a unittest environment
# the version will not be set when this is executed.
APP_VERSION = os.environ.get('CURRENT_VERSION_ID', '-1')


def ParseTweetDateString(date_str, tweet_id='', user_id=''):
  """Parses a date string from a tweet, returning 'now' on failure.

  Args:
    date_str: The date string to be parsed.
    tweet_id: The id of the tweet this date is being parsed from.
    user_id: The id of the user this date is being parsed from.
  """
  if not date_str:
    id_value, date_type = CalculateDateType(tweet_id, user_id)
    logging.warning('Empty creation date in %s id %s', date_type, id_value)
    return datetime.datetime.now()
  # We have to strip the UTC format because it is not supported on all
  # platforms.
  try:
    return datetime.datetime.strptime('%s %s' % (date_str[:-11], date_str[-4:]),
        DATE_PARSE_FMT_STR)
  except ValueError:
    logging.warning('Failed to parse date "%s" from tweet id %s',
        date_str, tweet_id)
    return datetime.datetime.now()
  # TODO: manually parse UTC offset and perform operation on resulting DT object?


def CalculateDateType(tweet_id, user_id):
  id_value = tweet_id or user_id
  if tweet_id:
    return ('tweet', id_value)
  return ('user', id_value)


def ParseIntegersFromTweet(entities, tweet_text):
  """Parses integers that don't occur in other entities.

  Args:
    entities: Entities object of other entities in the tweet
    tweet_text: The text of the tweet.

  Returns:
    A possibly empty list of IntegerEntity objects
  """
  ies = []
  if not tweet_text:
    return []
  for item in re.finditer(r'\d+', tweet_text):
    # Don't worry about really big numbers - they're not scores
    if len(item.group(0)) > 10:
      continue

    # Don't worry about numbers in other entities
    if entities.IsIndexInEntities(item.start(0), item.end(0)):
      continue
    ie = IntegerEntity()
    ie.num = long(item.group(0))
    ie.start_idx = int(item.start(0))
    ie.end_idx = int(item.end(0))
    ies.append(ie)

  return ies


def ParseGeoData(json_obj):
  """Return an ndb.GeoPt object from the 'geo' twitter json entry."""
  if not json_obj:
    return None
  if json_obj.get('type', '') != 'Point':
    return None
  pt_data = json_obj.get('coordinates', [])
  if not pt_data or len(pt_data) < 2:
    return None
  return ndb.GeoPt(pt_data[0], pt_data[1])


def ParsePlaceId(json_obj):
  """Parse the place id from the 'place' twitter tag if it exists."""
  if not json_obj:
    return None
  return json_obj.get('id', '')


class UserMentionEntity(ndb.Model):
  """Information about the mention of a user in a tweet."""
  user_id = ndb.StringProperty('id', required=True)

  # The character positions in the tweet where this entity started and ended.
  start_idx = ndb.IntegerProperty('si')
  end_idx = ndb.IntegerProperty('ei')

  @classmethod
  def fromJson(cls, json_obj):
    """Builds a UserMentionEntity object from a json object."""
    ume = UserMentionEntity()
    ume.user_id = json_obj.get('id_str', '')
    indices = json_obj.get('indices', [])
    if len(indices) < 2:
      return ume
    ume.start_idx = indices[0]
    ume.end_idx = indices[1]
    return ume


class UrlMentionEntity(ndb.Model):
  """Information about a URL in a tweet."""
  # URL as shown in tweet text.
  url = ndb.StringProperty('u', indexed=False)

  # Display URL for user.
  display_url = ndb.StringProperty('du', indexed=False)

  # Fully resolved URL.
  expanded_url = ndb.StringProperty('eu', indexed=False)

  # The character positions in the tweet where this entity started and ended.
  start_idx = ndb.IntegerProperty('si')
  end_idx = ndb.IntegerProperty('ei')

  @classmethod
  def fromJson(cls, json_obj):
    """Builds a UrlMentionEntity object from a json object."""
    ume = UrlMentionEntity()
    ume.display_url = json_obj.get('display_url')
    ume.url = json_obj.get('url')
    ume.expanded_url = json_obj.get('expanded_url')

    indices = json_obj.get('indices', [])
    if len(indices) < 2:
      return ume
    ume.start_idx = indices[0]
    ume.end_idx = indices[1]
    return ume

class HashTagEntity(ndb.Model):
  """Information about a hashtag in the tweet."""
  text = ndb.StringProperty()

  # The character positions in the tweet where this entity started and ended.
  start_idx = ndb.IntegerProperty('si')
  end_idx = ndb.IntegerProperty('ei')

  @classmethod
  def fromJson(cls, json_obj):
    """Builds a HashTagEntity object from a json object."""
    hte = HashTagEntity()
    hte.text = json_obj.get('text', '')
    indices = json_obj.get('indices', [])
    if len(indices) < 2:
      return ume
    hte.start_idx = indices[0]
    hte.end_idx = indices[1]
    return hte


class IntegerEntity(ndb.Model):
  """Information about an integer in the tweet.

  Note: this is *not* returned from the Twitter API, but it's important enough
  for Score minion that we parse it out for each tweet.
  """
  num = ndb.IntegerProperty()

  # The character positions in the tweet where this entity started and ended.
  start_idx = ndb.IntegerProperty('si')
  end_idx = ndb.IntegerProperty('ei')


class Entities(ndb.Model):
  """Item from the 'entities' tag in the API.

  More info: https://dev.twitter.com/overview/api/entities-in-twitter-objects
    and https://dev.twitter.com/overview/api/entities
  """
  hashtags = ndb.StructuredProperty(HashTagEntity, 'h', repeated=True)
  user_mentions = ndb.StructuredProperty(UserMentionEntity, 'usm', repeated=True)
  url_mentions = ndb.StructuredProperty(UrlMentionEntity, 'urm', repeated=True)
  integers = ndb.StructuredProperty(IntegerEntity, 'n', repeated=True)

  def IsIndexInEntities(self, start_idx, end_idx):
    """Returns True if this interval overlaps with another non-Integer entity interval."""
    for hashtag in self.hashtags:
      if start_idx >= hashtag.start_idx and start_idx < hashtag.end_idx:
        return True
    for um in self.user_mentions:
      if start_idx >= um.start_idx and start_idx < um.end_idx:
        return True
    for um in self.url_mentions:
      if start_idx >= um.start_idx and start_idx < um.end_idx:
        return True
    # Don't worry about integers because this is called by the integer-parsing code.
    return False

  # Major field this class is ignoring: media
  @classmethod
  def fromJson(cls, json_obj, tweet_text=''):
    """Builds a Entities object from a json object.

    Args:
      json_obj: The JSON object representing the Entities.
      tweet_text: The text of the tweet, if parsing of IntegerEntity objects
        is desired.
    Returns:
      An Entities object.
    """
    entities = Entities()
    for hashtag in json_obj.get('hashtags', []):
      parsed_ht = HashTagEntity.fromJson(hashtag)
      if parsed_ht:
        entities.hashtags.append(parsed_ht)
    for user_mention in json_obj.get('user_mentions', []):
      parsed_um = UserMentionEntity.fromJson(user_mention)
      if parsed_um:
        entities.user_mentions.append(parsed_um)
    for url_mention in json_obj.get('urls', []):
      parsed_um = UrlMentionEntity.fromJson(url_mention)
      if parsed_um:
        entities.url_mentions.append(parsed_um)
    entities.integers = ParseIntegersFromTweet(entities, tweet_text)
    return entities


class Tweet(ndb.Model):
  """Models an individual Tweet diplayed in a timeline.
  
  More info: https://dev.twitter.com/overview/api/tweets
  """
  # Author of the tweet
  author_id = ndb.StringProperty('a', required=True)

  # Date & time the tweet was authored
  created_at = ndb.DateTimeProperty('cd', required=True)

  # 64-bit, unique, stable id, but Keys should use strings, not ints, to avoid
  # key collisions with keys picked by the datastore
  # See: https://cloud.google.com/appengine/docs/python/ndb/entities#numeric_keys
  id_str = ndb.KeyProperty('id', required=True)

  # Text of tweet
  text = ndb.StringProperty('t')

  # Client used to post
  source = ndb.StringProperty('cli', indexed=False)

  # ID of tweet this is a reply to.
  in_reply_to_status_id = ndb.StringProperty('rts')

  # ID of user of the tweet this is in reply to.
  in_reply_to_user_id = ndb.StringProperty('rtu')

  # Geo-tag for where this was tweet from.
  # eg, "geo":{"type":"Point","coordinates":[37.779201,-122.4387313]},
  geo = ndb.GeoPtProperty('g')

  # When present, indicates the tweet is associated with (but not necessarily
  # tweeted from) a given place.
  #
  # Only the 'id' is stored here, but this is what this looks like in a response.
  # "place":{
  #     "id":"5a110d312052166f",
  #     "url":"https:\/\/api.twitter.com\/1.1\/geo\/id\/5a110d312052166f.json",
  #     "place_type":"city",
  #     "name":"San Francisco",
  #     "full_name":"San Francisco, CA",
  #     "country_code":"US",
  #     "country":"United States",
  #     "contained_within":[],
  #     "bounding_box":{
  #         "type":"Polygon","coordinates":[[[-122.514926,37.708075],
  #            [-122.514926,37.833238], [-122.357031,37.833238],
  #            [-122.357031,37.708075]]]}
  place_id = ndb.StringProperty('pl')

  # Number of times this has been retweeted.
  retweet_count = ndb.IntegerProperty('rc')

  # Number of times this has been favorited.
  favorite_count = ndb.IntegerProperty('fc')

  # Entities which have been parsed from the text of this tweet.
  entities = ndb.StructuredProperty(Entities, 'ents')

  # BCP 47 lang code: http://tools.ietf.org/html/bcp47
  lang = ndb.StringProperty('la')  # eg, "en"

  ##### Score minion-specific metadata about this object #####
  date_added = ndb.DateTimeProperty('da', auto_now_add=True)
  date_modified = ndb.DateTimeProperty('dm', auto_now=True)

  # Keep track of which version added this data
  # TODO: consider making this part of the key, and enforcing (somehow) that
  # an app only gets read access to the data in another version.
  added_by_app_version = ndb.StringProperty('ver', required=True)

  @classmethod
  def fromJson(cls, json_obj):
    """Builds a Tweet object from a json object."""
    id_str = json_obj.get('id_str', '')
    return Tweet(author_id=json_obj.get('user', {}).get('id_str', ''),
        id_str=ndb.Key(DEFAULT_TWEET_DB_NAME, id_str),
        created_at=ParseTweetDateString(
          json_obj.get('created_at', ''), tweet_id=id_str),
        added_by_app_version=APP_VERSION,
        text=json_obj.get('text', ''),
        source=json_obj.get('source', ''),
        in_reply_to_status_id=json_obj.get('in_reply_to_status_id_str', ''),
        in_reply_to_user_id=json_obj.get('in_reply_to_user_id_str', ''),
        geo=ParseGeoData(json_obj.get('geo', None)),
        place_id=ParsePlaceId(json_obj.get('place', {})),
        retweet_count = long(json_obj.get('retweet_count', 0)),
        favorite_count = long(json_obj.get('favorite_count', 0)),
        entities=Entities.fromJson(json_obj.get('entities', {}),
          tweet_text=json_obj.get('text', '')),
        lang=json_obj.get('lang', ''))


class User(ndb.Model):
  """Models a twitter user.
  
  More info: https://dev.twitter.com/overview/api/users
  """
  # Unique, stable, 64-bit id for the user.  Strings are used to avoid collisions
  # in the keyspace with auto-picked keys
  # See also: https://cloud.google.com/appengine/docs/python/ndb/entities#numeric_keys
  id_str = ndb.KeyProperty('id', required=True)

  # User-defined name
  name = ndb.StringProperty('n')  # eg, "Martin Cochran"

  # User-defined handle.  Can change.
  screen_name = ndb.StringProperty('sn')  # eg, "martin_cochran"

  # User-defined location - arbitrary string.
  location = ndb.StringProperty('l')

  # User-defined self-description.
  description = ndb.StringProperty('d')

  # User-supplied URL.
  url = ndb.StringProperty(indexed=False)

  # Entities related to the user.  We don't currently care about this since we
  # won't be displaying detailed information about the user description anywhere.
  # entities = ndb.StructuredProperty(Entities)

  # If true, user has chosen to protect their tweets.
  protected = ndb.BooleanProperty('p', indexed=False)

  # When was this user created?
  created_at = ndb.DateTimeProperty('cd')

  # Number of tweets this user has favorited in the account's lifetime.
  # English sp is consistent with Twitter API - whatever.
  favourites_count = ndb.IntegerProperty('f')

  # Offset from GMT/UTC in seconds.
  utc_offset = ndb.IntegerProperty('uo', indexed=False)

  # String describing time zone the user declares themselves in.
  time_zone = ndb.StringProperty('tz', indexed=False)

  # Has the user enabled the option of geo-tagging their tweets?
  geo_enabled = ndb.BooleanProperty('ge')

  # Spam control.
  verified = ndb.BooleanProperty('vfd', indexed=False)

  # Total # of tweets by the user.
  statuses_count = ndb.IntegerProperty('sc')

  # BCP 47 lang code: http://tools.ietf.org/html/bcp47
  lang = ndb.StringProperty('la')

  # URLs for displaying user icon / banner in tweets.
  profile_image_url_https = ndb.StringProperty('piu', indexed=False)
  profile_banner_url_https = ndb.StringProperty('pbu', indexed=False)

  # Number of people that follow this user.
  followers_count = ndb.IntegerProperty()

  # Number of people this user follows.
  friends_count = ndb.IntegerProperty()

  # Number of public lists this user is a member of.
  listed_count = ndb.IntegerProperty()

  ##### Score minion added data. #####
  # User ids of followers of this user.
  followers = ndb.StringProperty(repeated=True)

  # User ids of accounts this user follows.
  friends = ndb.StringProperty(repeated=True)

  ##### Score minion-specific metadata. #####
  date_added = ndb.DateTimeProperty('da', auto_now_add=True)
  date_modified = ndb.DateTimeProperty('dm', auto_now=True)

  # Keep track of which version of the app added this data 
  added_by_app_version = ndb.StringProperty('ver', required=True)

  @classmethod
  def fromJson(cls, json_obj):
    """Builds a User object from a json object."""
    id_str = json_obj.get('id_str', '')
    return User(id_str=ndb.Key(DEFAULT_AUTHOR_DB_NAME, id_str),
        name=json_obj.get('name', ''),
        screen_name=json_obj.get('screen_name', ''),
        location=json_obj.get('location', ''),
        description=json_obj.get('description', ''),
        url=json_obj.get('url', ''),
        created_at=ParseTweetDateString(
          json_obj.get('created_at', ''), user_id=id_str),
        protected=json_obj.get('protected', False),
        favourites_count=json_obj.get('favourites_count', 0L),
        utc_offset=json_obj.get('utc_offset', 0L),
        time_zone=json_obj.get('time_zone', ''),
        geo_enabled=json_obj.get('geo_enabled', False),
        verified=json_obj.get('verified', False),
        statuses_count=json_obj.get('statuses_count', 0L),
        lang=json_obj.get('lang', ''),
        profile_image_url_https=json_obj.get('profile_image_url_https', ''),
        profile_banner_url_https=json_obj.get('profile_banner_url', ''),
        followers_count=json_obj.get('followers_count', 0L),
        friends_count=json_obj.get('friends_count', 0L),
        added_by_app_version=APP_VERSION)