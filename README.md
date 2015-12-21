score-minion
============

Score reporter for ultimate frisbee tournaments that determines scores from
tweets and by crawling http://play.usaultimate.org

# Data model
There are two sources of games: Twitter and
[USAU Score Reporter](http://play.usaultimate.org/events/). There is
a simple data structure, game\_model.Team, which serves to join game
data between the sources. Team contains only the unique score reporter
team ID and the Twitter ID for each team.

There will be a weekly script to detect teams which are known via
score reporter but which are not regularly crawled by Twitter.
(TODO: this could be automated.)

The full data for each Twitter user or score reporter team is stored
in an object for each source (tweets.User and game\_model.FullTeamInfo,
respectively).

Author: Martin Cochran
