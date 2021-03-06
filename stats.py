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

import os

from google.appengine.ext.ndb import stats

import jinja2
import webapp2


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class StatsHandler(webapp2.RequestHandler):
  """Display some basic stats about the app."""
  def get(self):
    global_stat = stats.GlobalStat.query().get()
    if not global_stat:
      self.response.write('No stats available')
      return

    template_values = {
      'global_stats': global_stat,
    }
 
    template = JINJA_ENVIRONMENT.get_template('html/stats.html')
    self.response.write(template.render(template_values))

app = webapp2.WSGIApplication([
  ('/stats', StatsHandler),
], debug=True)
