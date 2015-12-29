#!/usr/bin/env python
#
# Copyright 2015 Martin Cochran
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

"""Utilities for comparing game scores."""

import logging

class Scores(object):
  """Class to represent a pair of scores in a game."""

  def __init__(self, home, away, ordered=False):
    """Builds scores objects.

    Args:
      home: home score
      away: away score
      ordered: If True, interpret scores as 'known' in the sense
        that we're not guessing which score relates to which team
        as from a Tweet. In practice, ordered=True will only be when
        the score is coming from score reporter.
    """
    self._home = home
    self._away = away
    self._ordered = ordered
    
  @staticmethod
  def FromList(scores, ordered=False):
    """Convenience function to build object from a list.
    
    Args:
      scores: list of integers of size 2.
    Raises:
      ValueError: if list is the wrong length
      TypeError: if list contents are not integers
    Returns:
      A Score object with the given scores in the list.
    """
    if not scores or len(scores) != 2:
      raise ValueError('Input array not correct length: %s' % scores)
    if type(scores[0]) != int or type(scores[1]) != int:
      raise TypeError('Input array not correct type: %s' % scores)
    return Scores(scores[0], scores[1], ordered=ordered)

  def __cmp__(self, other):
    if type(other) != Scores:
      return -1
    a = [self._home, self._away]
    b = [other._home, other._away]
    if not (self._ordered and other._ordered):
      a = sorted(a)
      b = sorted(b)
    home = cmp(a[0], b[0])
    away = cmp(a[1], b[1])
    if home >= 0 and away >= 0:
      return home + away
    if home < 0 and away < 0:
      return home + away
    # If this case is reached, then one of the scores is less
    # than the prior score, which means it had to have occured
    # at an earlier game state (or, more likely, from a different
    # game in the case where scores are being compared from Tweets).
    return -1

  def __str__(self):
    return '[%s, %s]' % (self._home, self._away)

  def __repr__(self):
    return self.__str__()
