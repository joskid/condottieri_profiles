## Copyright (c) 2010 by Jose Antonio Martin <jantonio.martin AT gmail DOT com>
## This program is free software: you can redistribute it and/or modify it
## under the terms of the GNU Affero General Public License as published by the
## Free Software Foundation, either version 3 of the License, or (at your option
## any later version.
##
## This program is distributed in the hope that it will be useful, but WITHOUT
## ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
## FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License
## for more details.
##
## You should have received a copy of the GNU Affero General Public License
## along with this program. If not, see <http://www.gnu.org/licenses/agpl.txt>.
##
## This license is also included in the file COPYING
##
## AUTHOR: Jose Antonio Martin <jantonio.martin AT gmail DOT com>

""" This application is meant to substitute the profiles in Pinax, so that the
profiles hold more information related to the game, such as scores, and karma.

"""

from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django.conf import global_settings
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

from transmeta import TransMeta

from machiavelli.signals import government_overthrown, player_joined, player_surrendered


if "notification" in settings.INSTALLED_APPS:
	from notification import models as notification
else:
	notification = None

KARMA_MINIMUM = settings.KARMA_MINIMUM
KARMA_DEFAULT = settings.KARMA_DEFAULT
KARMA_MAXIMUM = settings.KARMA_MAXIMUM

class CondottieriProfileManager(models.Manager):
	def hall_of_fame(self, order='weighted_score'):
		if not (order in CondottieriProfile._meta.get_all_field_names() \
			or order in ['avg_score', 'avg_victories']):
			order = 'weighted_score'
		order = ''.join(['-', order])
		return self.filter(total_score__gt=0, finished_games__gt=2).extra(
			select={'avg_victories': "100 * (victories / finished_games)",
				'avg_score': "total_score / finished_games"}).order_by(order)

class CondottieriProfile(models.Model):
	""" Defines the actual profile for a Condottieri user.

	"""
	user = models.ForeignKey(User, unique=True, verbose_name=_('user'))
	""" A User object related to the profile """
	name = models.CharField(_('name'), max_length=50, null=True, blank=True)
	""" The user complete name """
	about = models.TextField(_('about'), null=True, blank=True)
	""" More user info """
	location = models.CharField(_('location'), max_length=40, null=True, blank=True)
	""" Geographic location string """
	website = models.URLField(_("website"), null = True, blank = True, verify_exists = False)
	karma = models.PositiveIntegerField(default=KARMA_DEFAULT, editable=False)
	""" Total karma value """
	total_score = models.IntegerField(default=0, editable=False)
	""" Sum of game scores """
	weighted_score = models.IntegerField(default=0, editable=False)
	""" Sum of devaluated game scores """
	finished_games = models.PositiveIntegerField(default=0, editable=False)
	""" Number of games that the player has played to the end """
	victories = models.PositiveIntegerField(default=0, editable=False)
	""" Number of victories """
	overthrows = models.PositiveIntegerField(default=0, editable=False)
	""" Number of times that the player has been overthrown """
	surrenders = models.PositiveIntegerField(default=0, editable=False)
	""" Number of times that the player has surrendered """
	badges = models.ManyToManyField('Badge', verbose_name=_("badges"))
	is_editor = models.BooleanField(_("Is editor?"), default=False)

	objects = CondottieriProfileManager()

	def __unicode__(self):
		return self.user.username

	def get_absolute_url(self):
		return ('profile_detail', None, {'username': self.user.username})
	get_absolute_url = models.permalink(get_absolute_url)

	def has_languages(self):
		""" Returns true if the user has defined at least one known language """
		try:
			SpokenLanguage.objects.get(profile=self)
		except MultipleObjectsReturned:
			return True
		except ObjectDoesNotExist:
			return False
		else:
			return True

	def average_score(self):
		if self.finished_games > 0:
			return float(self.total_score) / self.finished_games
		else:	
			return 0
	
	def adjust_karma(self, k):
		""" Adds or substracts some karma to the total """
		if not isinstance(k, int):
			return
		new_karma = self.karma + k
		if new_karma > KARMA_MAXIMUM:
			new_karma = KARMA_MAXIMUM
		elif new_karma < KARMA_MINIMUM:
			new_karma = KARMA_MINIMUM
		self.karma = new_karma
		self.save()

	def overthrow(self):
		""" Add 1 to the overthrows counter of the profile """
		self.overthrows += 1
		self.save()

	def check_karma_to_join(self, fast=False, private=False):
		karma_to_join = getattr(settings, 'KARMA_TO_JOIN', 50)
		karma_to_fast = getattr(settings, 'KARMA_TO_FAST', 110)
		karma_to_private = getattr(settings, 'KARMA_TO_PRIVATE', 110)
		karma_to_unlimited = getattr(settings, 'KARMA_TO_UNLIMITED', 0)
		games_limit = getattr(settings, 'GAMES_LIMIT', 50)
		if self.karma < karma_to_join:
			return _("You need a minimum karma of %s to play a game.") % karma_to_join
		if fast and self.karma < karma_to_fast:
			return _("You need a minimum karma of %s to play a fast game.") % karma_to_fast
		if private and self.karma < karma_to_private:
			return _("You need a minimum karma of %s to create a private game.") % karma_to_private
		if self.karma < karma_to_unlimited:
			current_games = self.user.player_set.all().count()
			if current_games >= games_limit:
				return _("You need karma %s to play more than %s games.") % (karma_to_unlimited, games_limit)
		return ""
		

def add_overthrow(sender, **kwargs):
	if not sender.voluntary:
		profile = sender.government.get_profile()
		profile.overthrow()

government_overthrown.connect(add_overthrow)

def add_surrender(sender, **kwargs):
	profile = sender.user.get_profile()
	profile.surrenders += 1
	try:
		surrender_karma = settings.SURRENDER_KARMA
	except:
		surrender_karma = -10
	profile.adjust_karma(surrender_karma)

player_surrendered.connect(add_surrender)

def create_profile(sender, instance=None, **kwargs):
	""" Creates a profile associated to a User	"""
	if instance is None:
		return
	profile, created = CondottieriProfile.objects.get_or_create(user=instance)

post_save.connect(create_profile, sender=User)

class SpokenLanguage(models.Model):
	""" Defines a language that a User understands """
	code = models.CharField(_("language"), max_length=8, choices=global_settings.LANGUAGES)
	profile = models.ForeignKey(CondottieriProfile)

	def __unicode__(self):
		return self.get_code_display()
	
	class Meta:
		unique_together = (('code', 'profile',),)

class Friendship(models.Model):
	"""
	Defines a one-way friendship relationship between two users.
	"""
	friend_from = models.ForeignKey(User, related_name="friends")
	friend_to = models.ForeignKey(User, related_name="friend_of")
	created_on = models.DateTimeField(editable=False, auto_now_add=True)

	class Meta:
		unique_together = (('friend_from', 'friend_to',),)

	def __unicode__(self):
		return "%s is a friend of %s" % (self.friend_to, self.friend_from)

def was_befriended(sender, instance, created, **kwargs):
	""" Notify a user when other user befriends him """
	if notification and created:
		recipients = [instance.friend_to, ]
		extra_context = {'username': instance.friend_from,
						'STATIC_URL': settings.STATIC_URL,}
		notification.send(recipients, "new_friend", extra_context, on_site=True)

post_save.connect(was_befriended, sender=Friendship)

def friend_joined_game(sender, **kwargs):
	""" Notify a user if a friend joins a game """
	if notification:
		user = sender.user
		friend_of_ids = user.friend_of.values_list('friend_from', flat=True)
		recipients = []
		for f in user.friends.all():
			if f.friend_to.id in friend_of_ids:
				recipients.append(f.friend_to)
		extra_context = {'username': sender.user.username,
					'slug': sender.game.slug,
					'STATIC_URL': settings.STATIC_URL,}	
		notification.send(recipients, "friend_joined", extra_context, on_site=True)

player_joined.connect(friend_joined_game)

class Badge(models.Model):
	""" Defines an award or honor that a user may earn """
	__metaclass__ = TransMeta

	image = models.ImageField(_("image"), upload_to="badges")
	description = models.CharField(_("description"), max_length=200)

	class Meta:
		verbose_name = _("badge")
		verbose_name_plural = _("badges")
		translate = ('description',)

	def __unicode__(self):
		return u"%s" % self.description

