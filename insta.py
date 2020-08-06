from instagram_scraper import InstagramScraper as _InstagramScraper
import json
import tqdm
from instagram_scraper.constants import *
from tempfile import gettempdir


class Instagram:
    def __init__(self, guest=True, verbose=False, comments=False, **kwargs):
        if kwargs.get("login_user") and kwargs.get("login_pass"):
            guest = False
        self.instagram = self._get_scrapper(quiet=not verbose,
                                            comments=comments,
                                            **kwargs)
        if guest:
            self.instagram.authenticate_as_guest()
        else:
            self.instagram.authenticate_with_login()

    @staticmethod
    def _get_scrapper(quiet=True, comments=False, **kwargs):

        class _InstaScrap(_InstagramScraper):

            def get_profile_info(self, username):
                if self.profile_metadata is False:
                    return
                url = USER_URL.format(username)
                resp = self.get_json(url)

                if resp is None:
                    self.logger.error(
                        'Error getting user wifi_info for {0}'.format(
                            username))
                    return

                self.logger.info(
                    'Saving metadata general information on {0}.json'.format(
                        username))

                user_info = json.loads(resp)['graphql']['user']

                try:
                    profile_info = {
                        'biography': user_info['biography'],
                        'followers_count': user_info['edge_followed_by'][
                            'count'],
                        'following_count': user_info['edge_follow']['count'],
                        'full_name': user_info['full_name'],
                        'id': user_info['id'],
                        'is_business_account': user_info[
                            'is_business_account'],
                        'is_joined_recently': user_info['is_joined_recently'],
                        'is_private': user_info['is_private'],
                        'posts_count':
                            user_info['edge_owner_to_timeline_media']['count'],
                        'profile_pic_url': user_info['profile_pic_url']
                    }
                except (KeyError, IndexError, StopIteration):
                    self.logger.warning(
                        'Failed to build {0} profile wifi_info'.format(
                            username))
                    return

                return {
                    'GraphProfileInfo': {
                        'wifi_info': profile_info,
                        'username': username,
                        'created_time': 1286323200
                    }
                }

            def get_stories(self, user):
                """Scrapes the user's stories."""
                if self.logged_in and \
                        (
                                'story-image' in self.media_types or 'story-video' in self.media_types):
                    # Get the user's stories.
                    stories = self.fetch_stories(user['id'])

                    # Downloads the user's stories and sends it to the executor.
                    iter = 0
                    for item in tqdm.tqdm(stories,
                                          desc='Searching {0} for stories'.format(
                                              user['username']),
                                          unit=" media",
                                          disable=self.quiet):
                        if self.story_has_selected_media_types(
                                item) and self.is_new_media(item):
                            item['username'] = user['username']
                            item['shortcode'] = ''
                            yield item

                        iter = iter + 1
                        if self.maximum != 0 and iter >= self.maximum:
                            break

            def get_profile_pic(self, user):
                if 'image' not in self.media_types:
                    return

                if self.logged_in:
                    # Try Get the High-Resolution profile picture
                    url = USER_INFO.format(user['id'])
                    resp = self.get_json(url)

                    if resp is None:
                        self.logger.error(
                            'Error getting user wifi_info for {0}'.format(
                                user['username']))
                        return

                    user_info = json.loads(resp)['user']

                    if user_info['has_anonymous_profile_picture']:
                        return

                    try:
                        profile_pic_urls = [
                            user_info['hd_profile_pic_url_info']['url'],
                            user_info['hd_profile_pic_versions'][-1]['url'],
                        ]

                        profile_pic_url = next(
                            url for url in profile_pic_urls if url is not None)
                    except (KeyError, IndexError, StopIteration):
                        self.logger.warning(
                            'Failed to get high resolution profile picture for {0}'.format(
                                user['username']))
                        profile_pic_url = user['profile_pic_url_hd']
                else:
                    # If not logged_in take the Low-Resolution profile picture
                    profile_pic_url = user['profile_pic_url_hd']

                return {'urls': [profile_pic_url],
                        'username': user['username'], 'shortcode': '',
                        'created_time': 1286323200}

            def get_media(self, user):
                """Scrapes the user's posts for media."""
                if 'image' not in self.media_types and \
                        'video' not in self.media_types and \
                        'none' not in self.media_types:
                    return

                username = user['username']

                iter = 0
                for item in tqdm.tqdm(self.query_media_gen(user),
                                      desc='Searching {0} for posts'.format(
                                          username),
                                      unit=' media', disable=self.quiet):
                    if self.comments:
                        item['comments'] = {'data': list(
                            self.query_comments_gen(item['shortcode']))}

                    item['username'] = username
                    yield item

                    iter = iter + 1
                    if self.maximum != 0 and iter >= self.maximum:
                        break

            def _retry_prompt(self, url, exception_message):
                return False

            def _parse(self):
                """Crawls through and downloads user's media"""
                self.session.headers.update({'user-agent': STORIES_UA})
                try:
                    for username in self.usernames:
                        # Get the user metadata.
                        shared_data = self.get_shared_data(username)
                        user = self.deep_get(shared_data,
                                             'entry_data.ProfilePage[0].graphql.user')

                        if not user:
                            self.logger.error(
                                'Error getting user details for {0}. Please verify that the user exists.'.format(
                                    username))
                            continue
                        elif user and user['is_private'] and \
                                user['edge_owner_to_timeline_media'][
                                    'count'] > 0 and not \
                                user['edge_owner_to_timeline_media']['edges']:
                            self.logger.info(
                                'User {0} is private'.format(username))

                        try:

                            for item in self.get_media(user):
                                yield item
                        except ValueError:
                            self.logger.error(
                                "Unable to scrape user - %s" % username)
                finally:
                    self.quit = True
                    self.logout()

        return _InstaScrap(quiet=quiet, comments=comments,
                           log_destination=gettempdir(), **kwargs)

    def get_profile_info(self, usernames=None):
        usernames = usernames or self.instagram.usernames
        if isinstance(usernames, str):
            usernames = [usernames]
        self.instagram.usernames = usernames
        for username in usernames:
            yield {username: self.instagram.get_profile_info(username)}

    def get_stories(self, usernames=None):
        usernames = usernames or self.instagram.usernames
        if isinstance(usernames, str):
            usernames = [usernames]
        self.instagram.usernames = usernames
        for username in usernames:
            # Get the user metadata.
            shared_data = self.instagram.get_shared_data(username)
            user = self.instagram.deep_get(shared_data,
                                           'entry_data.ProfilePage[0].graphql.user')
            if not user:
                print(
                    "ERROR: unknown user {username}".format(username=username))
                return
            user["username"] = username
            for s in self.instagram.get_stories(user):
                yield s

    def get_shared_data(self, usernames=None):
        usernames = usernames or self.instagram.usernames
        if isinstance(usernames, str):
            usernames = [usernames]
        self.instagram.usernames = usernames

        for username in usernames:
            # Get the user metadata.
            shared_data = self.instagram.get_shared_data(username)
            yield shared_data

    def get_profile_pic(self, usernames=None):
        usernames = usernames or self.instagram.usernames
        if isinstance(usernames, str):
            usernames = [usernames]
        self.instagram.usernames = usernames

        for username in usernames:
            # Get the user metadata.
            shared_data = self.instagram.get_shared_data(username)
            user = self.instagram.deep_get(shared_data,
                                           'entry_data.ProfilePage[0].graphql.user')
            if not user:
                print(
                    "ERROR: unknown user {username}".format(username=username))
                return
            user["username"] = username

            yield self.instagram.get_profile_pic(user)

    def get_media(self, usernames=None):
        usernames = usernames or self.instagram.usernames
        if isinstance(usernames, str):
            usernames = [usernames]
        self.instagram.usernames = usernames
        for item in self.instagram._parse():
            try:

                if item.get("__typename", "") == "GraphImage":
                    content = {
                        "dimensions": item.get("dimensions"),
                        "text":
                            item['edge_media_to_caption']["edges"][0]["node"][
                                "text"],
                        "url": item["display_url"],
                        "item_id": item["id"],
                        "tags": item.get("tags", []),
                        "username": item["username"],
                        "comments": item.get("comments", {}).get("data", []),
                        "ts": item["taken_at_timestamp"]
                    }
                    yield content
            except:
                pass


def get_posts(user, skips=None):
    skips = skips or []
    posts = list(reversed(list(Instagram().get_media([user]))))
    post_ids = [i['item_id'] for i in posts]
    for idx, post in enumerate(post_ids):
        if post in skips:
            posts.pop(idx)
    return posts


if __name__ == "__main__":

    user = "futurismcartoons"
    skips = ['2135177480425138062', '2103822161740647491']
    for media in get_posts(user, skips):
        print(media)
