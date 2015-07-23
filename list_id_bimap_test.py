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
# limitations under the License

import unittest

import test_env_setup

import list_id_bimap

class ListIdBiMapTest(unittest.TestCase):

  def testIsomorphism(self):
    """Verify list is consistent on all known lists."""
    for list_id in list_id_bimap.ListIdBiMap.ALL_LISTS:
      division, age_bracket, league = self._GetListProperties(list_id)
      self.assertEquals(list_id, self._GetListId(division, age_bracket, league))

  def _GetListProperties(self, list_id):
    """Convenience method to save characters in the test cases.
    
    Returns the structured list properties for the given list id.
    """
    return list_id_bimap.ListIdBiMap.GetStructuredPropertiesForList(list_id)

  def _GetListId(self, division, age_bracket, league):
    """Convenience method to save characters in the test cases.
    
    Returns the list id for the given structured properties.
    """
    return list_id_bimap.ListIdBiMap.GetListId(division, age_bracket, league)
