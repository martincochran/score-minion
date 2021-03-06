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

import scores_messages

class ScoresMessagesTest(unittest.TestCase):

  def testSanityMessages(self):
    """Just verify there are no syntax errors in the protocol definitions."""
    scores_messages.GamesRequest()
    scores_messages.GamesResponse()
    scores_messages.GameInfoRequest()
    scores_messages.GameInfoResponse()
