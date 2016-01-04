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


import unittest

import games

class GamesTest(unittest.TestCase):
  """Unit tests for the Games utility class."""

  def testScoreCmp(self):
    """Verify score comparison."""
    # Format of list is:
    # - score of first (or 'left') game
    # - score of second (or 'right') game
    # - expected result of ordered comparing left >= right
    # - expected result of un-ordered comparing left >= right
    table = [
        [[0, 0], [0, 0], True, True],
        [[1, 0], [0, 0], True, True],
        [[0, 1], [0, 0], True, True],
        [[0, 0], [1, 0], False, False],
        [[0, 0], [0, 1], False, False],
        [[1, 1], [2, 0], False, False],
        [[2, 0], [1, 1], False, False],
        [[1, 1], [0, 2], False, False],
        [[0, 2], [1, 1], False, False],
        [[0, 0], [1, 1], False, False],
        [[1, 1], [0, 0], True, True],
        [[2, 0], [0, 1], False, True],
        [[0, 2], [1, 0], False, True],
        [[10, 11], [13, 5], False, False],
    ]

    for a, b, ordered_result, unordered_result in table:
      for ordered in [True, False]:
        l = games.Scores.FromList(a, ordered=ordered)
        r = games.Scores.FromList(b, ordered=ordered)
        if ordered:
          result = ordered_result
        else:
          result = unordered_result
        self.assertEqual(l >= r, result,
            msg='%s >= %s = %s, expected %s (ordered: %s)' % (
              a, b, not result, result, ordered))

  def testConstructorErrors(self):
    with self.assertRaises(ValueError):
      games.Scores.FromList(None)
    with self.assertRaises(ValueError):
      games.Scores.FromList([])
    with self.assertRaises(ValueError):
      games.Scores.FromList([0])
    with self.assertRaises(ValueError):
      games.Scores.FromList([0, 1, 2])
    with self.assertRaises(TypeError):
      games.Scores.FromList([0, '2'])
