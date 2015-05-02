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
import json
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


# We want operations on an individual user to be consistent.
def user_key(user_id, user_table_name=DEFAULT_AUTHOR_DB_NAME):
  return ndb.Key('User', '%s_%s' % (user_table_name, user_id)) 


# We want operations on an individual tweet to be consistent.
def tweet_key(tweet_id, tweet_table_name=DEFAULT_TWEET_DB_NAME):
  return ndb.Key('Tweet', '%s_%s' % (tweet_table_name, tweet_id)) 


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
  try:
    # Convert to UTC time by manually parsing the timedelta because it is not
    # supported on all platforms.
    td = ParseUtcTimeDelta(date_str[-10:-5])
    return datetime.datetime.strptime('%s %s' % (date_str[:-11], date_str[-4:]),
        DATE_PARSE_FMT_STR) + td
  except ValueError:
    logging.warning('Failed to parse date "%s" from tweet id %s, user id %s',
        date_str, tweet_id, user_id)
    return datetime.datetime.now()


def ParseUtcTimeDelta(td_str):
  """Manually parse the UTC timedelta from the string (not supported some places).

  Args:
    td_str: Timedelta string of the form specified for the '%z' format
      specifier in strftime.
  Returns:
    A timedelta object.
  """
  # The most common case - let's make this easy.
  if td_str == '+0000':
    return datetime.timedelta(0, 0, 0)
  if td_str[0] not in ['-', '+'] or len(td_str) != 5:
    logging.warning('Bad UTC offset: %s', td_str)
    return datetime.timedelta(0, 0, 0)
  try:
    int(td_str[1:5])
  except ValueError:
    logging.warning('Bad UTC offset: %s', td_str)
    return datetime.timedelta(0, 0, 0)

  seconds = int(td_str[1:3])*3600 + int(td_str[3:])*60
  if td_str[0] == '-':
    return datetime.timedelta(0, seconds, 0)
  return datetime.timedelta(-1, (24 * 3600) - seconds, 0)


def WriteTweetDateString(dt):
  return '%s +0000 %s' % (dt.strftime('%a %b %d %H:%M:%S'), dt.strftime('%Y'))


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
  for item in re.finditer(r'\$?[\d:.,]+', tweet_text):
    # Don't worry about big numbers - they're not scores
    if len(item.group(0)) > 3:
      continue

    # If we didn't match any numbers, move on
    if not re.findall(r'\d+', item.group(0)):
      continue

    # Don't worry about money amounts
    if '$' in item.group(0)[0]:
      continue

    # Numbers with commas are not scores, but don't worry about trailing commas
    if '.' in item.group(0)[:-1]:
      continue

    # Neither are decimal numbers
    if ',' in item.group(0)[:-1]:
      continue

    # Neither are decimal numbers
    if ':' in item.group(0):
      continue

    # Don't worry about numbers in other entities
    if entities.IsIndexInEntities(item.start(0), item.end(0)):
      continue
    ie = IntegerEntity()
    number_text = item.group(0)
    end_offset = 0
    if number_text[-1] in ['.', ',']:
      number_text = number_text[:-1]
      end_offset = -1

    ie.num = long(number_text)
    ie.start_idx = int(item.start(0))
    ie.end_idx = int(item.end(0) + end_offset)

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

  # ID property as a 64-bit signed int. This will eventually replace user_id as
  # the main property.
  user_id_64 = ndb.IntegerProperty('id_64')

  # The character positions in the tweet where this entity started and ended.
  start_idx = ndb.IntegerProperty('si')
  end_idx = ndb.IntegerProperty('ei')

  @classmethod
  def fromJson(cls, json_obj):
    """Builds a UserMentionEntity object from a json object."""
    ume = UserMentionEntity()
    ume.user_id = json_obj.get('id_str', '')
    ume.user_id_64 = json_obj.get('id', 0)
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
      return hte
    hte.start_idx = indices[0]
    hte.end_idx = indices[1]
    return hte


class MediaEntity(ndb.Model):
  """Information about media (eg, a link to a photo) in the tweet."""
  # We don't save most of the info, we're mostly just interested in the indices
  url_https = ndb.StringProperty(indexed=False)
  id_str = ndb.StringProperty(indexed=False)

  # The character positions in the tweet where this entity started and ended.
  start_idx = ndb.IntegerProperty('si')
  end_idx = ndb.IntegerProperty('ei')

  @classmethod
  def fromJson(cls, json_obj):
    """Builds a MediaEntity object from a json object."""
    ment = MediaEntity()
    ment.url_https = json_obj.get('media_url_https', '')
    ment.id_str = json_obj.get('id_str', '')
    indices = json_obj.get('indices', [])
    if len(indices) < 2:
      return ment
    ment.start_idx = indices[0]
    ment.end_idx = indices[1]
    return ment


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
  media = ndb.StructuredProperty(MediaEntity, 'me', repeated=True)
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
    for ment in self.media:
      if start_idx >= ment.start_idx and start_idx < ment.end_idx:
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
    for media_entity in json_obj.get('media', []):
      parsed_ment = MediaEntity.fromJson(media_entity)
      if parsed_ment:
        entities.media.append(parsed_ment)
    entities.integers = ParseIntegersFromTweet(entities, tweet_text)
    return entities


class Tweet(ndb.Model):
  """Models an individual Tweet diplayed in a timeline.
  
  More info: https://dev.twitter.com/overview/api/tweets
  """
  # Author of the tweet
  author_id = ndb.StringProperty('a', required=True)

  # 64-bit integer form of author ID
  author_id_64 = ndb.IntegerProperty('a64')

  # Screen name of the author
  # TODO: remove.  We'll look this up on demand using memcache.
  author_screen_name = ndb.StringProperty('an', required=True)

  # Date & time the tweet was authored
  created_at = ndb.DateTimeProperty('cd', required=True)

  # ID property as a 64-bit signed int. This will eventually replace id_str as
  # the main property.
  id_64 = ndb.IntegerProperty()

  # 64-bit, unique, stable id, but Keys should use strings, not ints, to avoid
  # key collisions with keys picked by the datastore
  # See: https://cloud.google.com/appengine/docs/python/ndb/entities#numeric_keys
  id_str = ndb.StringProperty('id', required=True)

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

  # Eventually I might deprecate this, but it's staying until parsing bugs are
  # worked out.
  original_json = ndb.TextProperty('json', compressed=True)

  ##### Score minion-specific metadata about this object #####
  date_added = ndb.DateTimeProperty('da', auto_now_add=True)
  date_modified = ndb.DateTimeProperty('dm', auto_now=True)
  num_entities = ndb.ComputedProperty(lambda self: len(self.entities.integers), 'ne')
  two_or_more_integers = ndb.ComputedProperty(
      lambda self: len(self.entities.integers) > 1, 'tom')

  # The list ID if this tweet was indexed by getting statuses from a list.
  from_list = ndb.StringProperty('fl')

  # Keep track of which version added this data
  added_by_app_version = ndb.StringProperty('ver', required=True)

  @classmethod
  def getOrInsertFromJson(cls, json_obj, from_list=None):
    """Builds a Tweet object from a json object."""
    return cls.__BuildConstructorArgs(json_obj, True, from_list=from_list)

  @classmethod
  def fromJson(cls, json_obj, from_list=None):
    """Builds a Tweet object from a json object."""
    return Tweet.__BuildConstructorArgs(json_obj, False, from_list=from_list)

  @classmethod
  def __BuildConstructorArgs(cls, json_obj, insert, from_list=None):
    id_str = json_obj.get('id_str', '')
    if not id_str:
      logging.warning('could not parse tweet, no id_str: %s', json_obj)
      return None
    id_64 = json_obj.get('id', 0)
    if not id_64:
      logging.warning('could not parse tweet, no id: %s', json_obj)
      return None
    # todo: async?
    return Tweet.__BuildObject(id_str, insert, parent=tweet_key(id_str),
        author_id=json_obj.get('user', {}).get('id_str', ''),
        author_id_64=json_obj.get('user', {}).get('id', 0),
        author_screen_name=json_obj.get('user', {}).get('screen_name', ''),
        id_64=id_64,
        id_str=id_str,
        created_at=ParseTweetDateString(
          json_obj.get('created_at', ''), tweet_id=id_str),
        added_by_app_version=APP_VERSION,
        from_list=from_list,
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
        original_json=json.dumps(json_obj),
        lang=json_obj.get('lang', ''))

  @classmethod
  def __BuildObject(cls, tweet_id, insert, **kwargs):
    if insert:
      return Tweet.get_or_insert('id_str', **kwargs)
    else:
      return cls(id=tweet_id, **kwargs)

  # TODO: Don't use java camel-casing.
  def toJsonString(self):
    """Write this object to json string.
    
    Only suitable for testing at the moment.  Not idempotent when composed with
    calls to fromJson.
    """
    d = {}
    d['user'] = {
      'id_str': self.author_id,
      'id': self.author_id_64,
      'screen_name': self.author_screen_name
    }
    d['id_str'] = self.id_str
    d['id'] = self.id_64

    if self.created_at:
      d['created_at'] = WriteTweetDateString(self.created_at)
    return json.dumps(d)


class User(ndb.Model):
  """Models a twitter user.
  
  More info: https://dev.twitter.com/overview/api/users
  """
  # Unique, stable, 64-bit id for the user.  Strings are used to avoid collisions
  # in the keyspace with auto-picked keys
  # See also: https://cloud.google.com/appengine/docs/python/ndb/entities#numeric_keys
  id_str = ndb.StringProperty('id', required=True)

  # ID property as a 64-bit signed int. This will eventually replace id_str as
  # the main property.
  id_64 = ndb.IntegerProperty()

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
  def getOrInsertFromJson(cls, json_obj):
    """Builds a User object from a json object."""
    return cls.__BuildConstructorArgs(json_obj, True)

  @classmethod
  def fromJson(cls, json_obj):
    """Builds a User object from a json object."""
    return User.__BuildConstructorArgs(json_obj, False)

  @classmethod
  def __BuildConstructorArgs(cls, json_obj, insert):
    id_str = json_obj.get('id_str', '')
    if not id_str:
      logging.warning('could not parse tweet, no id_str: %s', json_obj)
      return None
    id_64 = json_obj.get('id', 0)
    if not id_64:
      logging.warning('could not parse tweet, no id: %s', json_obj)
      return None
    # todo: async?
    return User.__BuildObject(id_str, insert, parent=user_key(id_str),
        id_str=id_str,
        id_64=id_64,
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

  @classmethod
  def __BuildObject(cls, user_id, insert, **kwargs):
    if insert:
      return User.get_or_insert('id_str', **kwargs)
    else:
      return cls(id=user_id, **kwargs)
