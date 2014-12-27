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

DEFAULT_TWEET_DB_NAME = 'tweet_db'

DEFAULT_AUTHOR_DB_NAME = 'author_db'

# What should the ancestor keys look like?  Probably by id...
# TODO: Key property?  Probably int_id
# TODO: Default values?
class Tweet(ndb.Model):
  """Models an individual Tweet diplayed in a timeline.
  
  More info: https://dev.twitter.com/overview/api/tweets
  """
  # Author of the tweet
  author_id = ndb.IntegerProperty('a', required=True)

  # Date & time the tweet was authored
  created_at = ndb.DateTimeProperty('cd', required=True)

  # 64-bit, unique, stable id.
  int_id = ndb.IntegerProperty('id', required=True)

  # Text of tweet
  text = ndb.StringProperty('t')

  # Client used to post
  source = ndb.StringProperty('cli')

  # ID of tweet this is a reply to.
  in_reply_to_status_id = ndb.IntegerProperty('rts')

  # ID of user of the tweet this is in reply to.
  in_reply_to_user_id = ndb.IntegerProperty('rtu')

  # Geo-tag for where this was tweet from.
  # eg, "geo":{"type":"Point","coordinates":[37.779201,-122.4387313]},
  geo = ndb.GeoPtProperty('g')

  # "coordinates":{"type":"Point","coordinates":[-122.4387313,37.779201]}
  coordinates = ndb.GeoPtProperty('coord')

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
  entities = Entities('ents', repeated=True)

  # Has this been favorited by the authenticating user?
  favorited = ndb.BooleanProperty('f')

  # Has this been retweeted by the authenticating user?
  retweeted = ndb.BooleanProperty('r')

  # BCP 47 lang code: http://tools.ietf.org/html/bcp47
  lang = ndb.StringProperty('la')  # eg, "en"

  ##### Score minion-specific metadata about this object #####
  date_added = ndb.DateTimeProperty('da', auto_now_add=True)
  date_modified = ndb.DateTimeProperty('dm', auto_now=True)

  # Keep track of which version added this data
  added_by_app_version = ndb.IntegerProperty('ver', required=True)


class Entities(ndb.Model):
  """Item from the 'entities' tag in the API.

  More info: https://dev.twitter.com/overview/api/entities-in-twitter-objects
    and https://dev.twitter.com/overview/api/entities
  """
  hashtags = ndb.StructuredProperty('h', HashTag, repeated=True)
  user_mentions = ndb.StructuredProperty('usm', UserMention, repeated=True)
  url_mentions = ndb.StructuredProperty('urm', UrlMention, repeated=True)

  # Major field this class is ignoring: media


class UserMention(ndb.Model):
  """Information about the mention of a user in a tweet."""
  user_id = ndb.IntegerProperty('id', required=True)
  indicies = ndb.IntegerProperty('idxs', repeated=True)


class UrlMention(ndb.Model):
  """Information about a URL in a tweet."""
  # URL as shown in tweet text.
  url = ndb.StringProperty('u')

  # Display URL for user.
  display_url = ndb.StringProperty('du')

  # Fully resolved URL.
  expanded_url = ndb.StringProperty('eu')
  indicies = ndb.IntegerProperty('idxs', repeated=True)


class HashTag(ndb.Model):
  """Information about a hashtag in the tweet."""
  text = ndb.StringProperty()
  indicies = ndb.IntegerProperty('idxs', repeated=True)
  

class User(ndb.Model):
  """Models a twitter user.
  
  More info: https://dev.twitter.com/overview/api/users
  """
  # Unique, stable, 64-bit id for the user.
  user_id = ndb.IntegerProperty('id', required=True)

  # User-defined name
  name = ndb.StringProperty('n')  # eg, "Martin Cochran"

  # User-defined handle.  Can change.
  screen_name = ndb.StringProperty('sn')  # eg, "martin_cochran"

  # User-defined location - arbitrary string.
  location = ndb.StringProperty('l')

  # User-defined self-description.
  description = ndb.StringProperty('d')

  # User-supplied URL.
  url = ndb.StringProperty()

  # Entities related to the user
  entities = ndb.StructuredProperty(Entities, repeated=True)

  # If true, user has chosen to protect their tweets.
  protected = ndb.BooleanProperty('p')

  # When was this user created?
  created_at = ndb.DateTimeProperty('cd')

  # Number of tweets this user has favorited in the account's lifetime.
  favourites_count = ndb.IntegerProperty('f')

  # Offset from GMT/UTC in seconds.
  utc_offset = ndb.IntegerProperty('uo')

  # String describing time zone the user declares themselves in.
  time_zone = ndb.StringProperty('tz')

  # Has the user enabled the option of geo-tagging their tweets?
  geo_enabled = ndb.BooleanProperty('ge')

  # Spam control.
  verified = ndb.BooleanProperty('vfd')

  # Total # of tweets by the user.
  statuses_count = ndb.IntegerProperty('sc')

  # BCP 47 lang code: http://tools.ietf.org/html/bcp47
  lang = ndb.StringProperty('la')

  # URLs for displaying user icon / banner in tweets.
  profile_image_url_https = ndb.StringProperty('piu')
  profile_banner_url_https = ndb.StringProperty('pbu')


  # Number of people that follow this user.
  followers_count = ndb.IntegerProperty()

  # Number of people this user follows.
  friends_count = ndb.IntegerProperty()

  # Number of public lists this user is a member of.
  listed_count = ndb.IntegerProperty()

  ##### Score minion added data. #####
  # Followers of this user.
  followers = ndb.StringProperty(repeated=True)

  # Accounts this user follows.
  friends = ndb.StringProperty(repeated=True)

  ##### Score minion-specific metadata. #####
  date_added = ndb.DateTimeProperty('da', auto_now_add=True)
  date_modified = ndb.DateTimeProperty('dm', auto_now=True)

  # Keep track of which version of the app added this data 
  added_by_app_version = ndb.IntegerProperty('ver')
