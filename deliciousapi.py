"""
    Unofficial Python API for retrieving data from delicious.com.

    This module provides the following features plus some more:

    * getting a url's full public bookmarking history including
        * users who bookmarked the url including tags used for such bookmarks
      	  and the creation time of the bookmark (up to YYYY-MM-DD granularity)
        * top tags (up to a maximum of 10) including tag count
        * title as stored on delicious.com
        * total number of bookmarks/users for this url at delicious.com
    * getting a user's full bookmark collection, including any private bookmarks
      if you know the corresponding password
    * getting a user's full public tagging vocabulary, i.e. tags and tag counts
    * HTTP proxy support
    * updated to support delicious.com "version 2" (mini-relaunch as of August 2008)

    The official delicious.com API and the JSON/RSS feeds do not provide all
    the functionality mentioned above, and in such cases this module will query
    the delicious.com *website* directly and extract the required information
    by parsing the HTML code of the resulting web pages (a kind of poor man's
    web mining). The module is able to detect IP throttling, which is employed
    by delicious.com to temporarily block abusive HTTP request behavior, and
    will raise a custom Python error to indicate that. Please be a nice netizen
    and do not stress the delicious.com service more than necessary.

    It is strongly advised that you read the delicious.com Terms of Use
    before using this Python module. In particular, read section 5
    'Intellectual Property'.

    The code is licensed to you under version 2 of the GNU General Public
    License.

    More information about this module can be found at
    http://www.michael-noll.com/wiki/Del.icio.us_Python_API

    Copyright 2006-2008 Michael G. Noll <http://www.michael-noll.com/>

"""

__author__ = "Michael G. Noll"
__copyright__ = "(c) 2006-2008 Michael G. Noll"
__description__ = "Unofficial Python API for retrieving data from del.icio.us / delicious.com"
__email__ = "coding[AT]michael-REMOVEME-noll[DOT]com"
__license__ = "GPLv2"
__maintainer__ = "Michael G. Noll"
__status__ = "Development"
__url__ = "http://www.michael-noll.com/"
__version__ = "1.5.3"

import base64
import cgi
import datetime
import md5
from operator import itemgetter
import re
import socket
import time
import urllib2
import xml.dom.minidom

try:
    from BeautifulSoup import BeautifulSoup
except:
    print "ERROR: could not import BeautifulSoup Python module"
    print
    print "You can download BeautifulSoup from the Python Cheese Shop at"
    print "http://cheeseshop.python.org/pypi/BeautifulSoup/"
    print "or directly from http://www.crummy.com/software/BeautifulSoup/"
    print
    raise

try:
    import simplejson
except:
    print "ERROR: could not import simplejson module"
    print
    print "Since version 1.5.0, DeliciousAPI requires the simplejson module."
    print "You can download simplejson from the Python Cheese Shop at"
    print "http://pypi.python.org/pypi/simplejson"
    print
    raise


class DeliciousUser(object):
    """This class wraps all available information about a user into one object.

    Variables:
        bookmarks:
            A list of (user, tags, title, comment, timestamp) tuples representing
            a user's bookmark collection.

            url is a 'unicode'
            tags is a 'list' of 'unicode' ([] if no tags)
            title is a 'unicode'
            comment is a 'unicode' (u"" if no comment)
            timestamp is a 'datetime.datetime'

        tags (read-only property):
            A list of (tag, tag_count) tuples, aggregated over all a user's
            retrieved bookmarks. The tags represent a user's tagging vocabulary.

        username:
            The delicious.com account name of the user.

    """

    def __init__(self, username, bookmarks=None):
        assert username
        self.username = username
        self.bookmarks = bookmarks or []

    def __str__(self):
        total_tag_count = 0
        total_tags = set()
        for url, tags, title, comment, timestamp in self.bookmarks:
            total_tag_count += len(tags)
            for tag in tags:
                total_tags.add(tag)
        return "[%s] %d bookmarks, %d tags (%d unique)" % \
                    (self.username, len(self.bookmarks), total_tag_count, len(total_tags))

    def __repr__(self):
        return self.username

    def get_tags(self):
        """Returns a dictionary mapping tags to their tag count.

        For example, if the tag count of tag 'foo' is 23, then
        23 bookmarks were annotated with 'foo'. A different way
        to put it is that 23 users used the tag 'foo' when
        bookmarking the URL.

        """
        total_tags = {}
        for url, tags, title, comment, timestamp in self.bookmarks:
            for tag in tags:
                total_tags[tag] = total_tags.get(tag, 0) + 1 
        return total_tags
    tags = property(fget=get_tags, doc="Returns a dictionary mapping tags to their tag count")


class DeliciousURL(object):
    """This class wraps all available information about a web document into one object.

    Variables:
        bookmarks:
            A list of (user, tags, comment, timestamp) tuples, representing a
            document's bookmark history. Generally, this variable is populated
            via get_url(), so the number of bookmarks available in this variable
            depends on the parameters of get_url(). See get_url() for more
            information.

            user is a 'unicode'
            tags is a 'list' of 'unicode's ([] if no tags)
            comment is a 'unicode' (u"" if no comment)
            timestamp is a 'datetime.datetime' (granularity: creation *day*,
                i.e. the day but not the time of day)

        tags (read-only property):
            A list of (tag, tag_count) tuples, aggregated over all a document's
            retrieved bookmarks.

        top_tags:
            A list of (tag, tag_count) tuples, representing a document's so-called
            "top tags", i.e. the up to 10 most popular tags for this document.

        url:
            The URL of the document.

        hash (read-only property):
            The MD5 hash of the URL.

        title:
            The document's title.

        total_bookmarks:
            The number of total bookmarks (posts) of the document.

    """

    def __init__(self, url, top_tags=None, bookmarks=None, title=u"", total_bookmarks=0):
        assert url
        self.url = url
        self.top_tags = top_tags or []
        self.bookmarks = bookmarks or []
        self.title = title
        self.total_bookmarks = total_bookmarks

    def __str__(self):
        total_tag_count = 0
        total_tags = set()
        for user, tags, comment, timestamp in self.bookmarks:
            total_tag_count += len(tags)
            for tag in tags:
                total_tags.add(tag)
        return "[%s] %d total bookmarks (= users), %d tags (%d unique), %d out of 10 max 'top' tags" % \
                    (self.url, self.total_bookmarks, total_tag_count, \
                    len(total_tags), len(self.top_tags))

    def __repr__(self):
        return self.url

    def get_tags(self):
        """Returns a dictionary mapping tags to their tag count.

        For example, if the tag count of tag 'foo' is 23, then
        23 bookmarks were annotated with 'foo'. A different way
        to put it is that 23 users used the tag 'foo' when
        bookmarking the URL.

        """
        total_tags = {}
        for user, tags, comment, timestamp in self.bookmarks:
            for tag in tags:
                total_tags[tag] = total_tags.get(tag, 0) + 1
        return total_tags
    tags = property(fget=get_tags, doc="Returns a dictionary mapping tags to their tag count")

    def get_hash(self):
        m = md5.new(self.url)
        return m.hexdigest()
    hash = property(fget=get_hash, doc="Returns the MD5 hash of the URL of this document")


class DeliciousAPI(object):
    """
    This class provides a custom, unofficial API to the delicious.com service.

    Instead of using just the functionality provided by the official
    delicious.com API (which has limited features), this class retrieves
    information from the delicious.com website directly and extracts data from
    the web pages.

    Note that delicious.com will block clients with too many queries in a
    certain time frame (similar to their API throttling). So be a nice citizen
    and don't stress their website.

    """

    def __init__(self,
                    http_proxy="",
                    tries=3,
                    wait_seconds=3,
                    user_agent="DeliciousAPI/%s (+http://www.michael-noll.com/wiki/Del.icio.us_Python_API)" % __version__,
                    timeout=30,
        ):
        """Set up the API module.

        Parameters:
            http_proxy (optional)
                Use an HTTP proxy for HTTP connections. Proxy support for
                HTTPS is not available yet.
                Format: "hostname:port" (e.g., "localhost:8080")

            tries (optional, default: 3):
                Try the specified number of times when downloading a
                monitored document fails. tries must be >= 1.
                See also wait_seconds.

            wait_seconds (optional, default: 3):
                Wait the specified number of seconds before re-trying to
                download a monitored document. wait_seconds must be >= 0.
                See also tries.

            user_agent (optional, default: "DeliciousAPI/<version> (+http://www.michael-noll.com/wiki/Del.icio.us_Python_API)")
                Set the User-Agent HTTP Header.

            timeout (optional, default: 30):
                Set network timeout. timeout must be >= 0.

        """
        assert tries >= 1
        assert wait_seconds >= 0
        assert timeout >= 0
        self.http_proxy = http_proxy
        self.tries = tries
        self.wait_seconds = wait_seconds
        self.user_agent = user_agent
        self.timeout = timeout
        socket.setdefaulttimeout(self.timeout)


    def _query(self, path, host="delicious.com", user=None, password=None, use_ssl=False):
        """Queries delicious for information, specified by (query) path.

        Returns None on errors (i.e. on all HTTP status other than 200).
        On success, returns the content of the HTML response.

        """
        opener = None
        handlers = []

        # add HTTP Basic authentication if available
        if user and password:
            pwd_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
            pwd_mgr.add_password(None, host, user, password)
            basic_auth_handler = urllib2.HTTPBasicAuthHandler(pwd_mgr)
            handlers.append(basic_auth_handler)

        # add proxy support if requested
        if self.http_proxy:
            proxy_handler = urllib2.ProxyHandler({'http': 'http://%s' % self.http_proxy})
            handlers.append(proxy_handler)

        if handlers:
            opener = urllib2.build_opener(*handlers)
        else:
            opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', self.user_agent)]

        data = None
        tries = self.tries

        if use_ssl:
            protocol = "https"
        else:
            protocol = "http"
        url = "%s://%s%s" % (protocol, host, path)

        while tries > 0:
            try:
                f = opener.open(url)
                data = f.read()
                f.close()
            except urllib2.HTTPError, e:
                if e.code == 301:
                    raise DeliciousMovedPermanentlyWarning, "delicious.com status %s - url moved permanently" % e.code
                if e.code == 302:
                    raise DeliciousMovedTemporarilyWarning, "delicious.com status %s - url moved temporarily" % e.code
                elif e.code == 401:
                    raise DeliciousUnauthorizedError, "delicious.com error %s - unauthorized (authentication failed?)" % e.code
                elif e.code == 404:
                    raise DeliciousNotFoundError, "delicious.com error %s - url not found" % e.code
                elif e.code == 500:
                    raise Delicious500Error, "delicious.com error %s - server problem" % e.code
                elif e.code == 503 or e.code == 999:
                    raise DeliciousThrottleError, "delicious.com error %s - unable to process request (your IP address has been throttled/blocked)" % e.code
                else:
                    raise DeliciousUnknownError, "delicious.com error %s - unknown error" % e.code
                break
            except urllib2.URLError, e:
                time.sleep(self.wait_seconds)
            except socket.error, msg:
                # sometimes we get a "Connection Refused" error
                # wait a bit and then try again
                time.sleep(self.wait_seconds)
            #finally:
            #    f.close()
            tries -= 1
        return data


    def get_url(self, url, max_bookmarks=50, sleep_seconds=1):
        """Returns a DeliciousURL instance representing the delicious.com history of url.

        Generally, this method is what you want for getting title, bookmark, tag,
        and user information about a URL.

        Delicious only returns up to 50 bookmarks per URL. This means that
        we have to do subsequent queries plus parsing if we want to retrieve
        more than 50. Roughly speaking, the processing time of get_url()
        increases linearly with the number of 50-bookmarks-chunks; i.e.
        it will take 10 times longer to retrieve 500 bookmarks than 50.

        Parameters:
            url
                The URL of the web document to be queried for.

            max_bookmarks (optional, default: 50)
                See the documentation of get_bookmarks() for more
                information as get_url() uses get_bookmarks() to
                retrieve a url's bookmarking history.

            sleep_seconds (optional, default: 1)
                See the documentation of get_bookmarks() for more
                information as get_url() uses get_bookmarks() to
                retrieve a url's bookmarking history.

        """
        # we must wait at least 1 second between subsequent queries to
        # comply with delicious' Terms of Use
        assert sleep_seconds >= 1

        document = DeliciousURL(url)

        m = md5.new(url)
        hash = m.hexdigest()

        path = "/v2/json/urlinfo/%s" % hash
        data = self._query(path, host="feeds.delicious.com")
        if data:
            urlinfo = {}
            try:
                urlinfo = simplejson.loads(data)
                if urlinfo:
                    urlinfo = urlinfo[0]
            except TypeError:
                pass
            try:
                document.title = urlinfo['title'] or u""
            except KeyError:
                pass
            try:
                top_tags = urlinfo['top_tags'] or {}
                if top_tags:
                    document.top_tags = sorted(top_tags.iteritems(), key=itemgetter(1), reverse=True)
                else:
                    document.top_tags = []
            except KeyError:
                pass
            try:
                document.total_bookmarks = int(urlinfo['total_posts'])
            except KeyError, ValueError:
                pass
            document.bookmarks = self.get_bookmarks(url=url, max_bookmarks=max_bookmarks, sleep_seconds=sleep_seconds)


        return document

    def get_bookmarks(self, url=None, username=None, max_bookmarks=50, sleep_seconds=1):
        """
        Returns the bookmarks of url or user, respectively.

        For urls, it returns a list of (user, tags, comment, timestamp) tuples.
        For users, it returns a list of (url, tags, title, comment, timestamp) tuples.

        Bookmarks are sorted "descendingly" by creation time, i.e. newer
        bookmarks are first.

        Delicious only returns up to 50 bookmarks per URL on its website.
        This means that we have to do subsequent queries plus parsing if
        we want to retrieve more than 50. Roughly speaking, the processing
        time of get_bookmarks() increases linearly with the number of
        50-bookmarks-chunks; i.e. it will take 10 times longer to retrieve
        500 bookmarks than 50.

        Parameters:
            url
                The URL of the web document to be queried for.
                Cannot be used together with 'username'.

            username
                The username to be queried for.
                Cannot be used together with 'url'.

            max_bookmarks (optional, default: 50)
                Maximum number of bookmarks to retrieve. Set to 0 to disable
                this limitation/the maximum and retrieve all available
                bookmarks of the given url.

                Bookmarks are sorted so that newer bookmarks are first.
                Setting max_bookmarks to 50 means that get_bookmarks() will retrieve
                the 50 most recent bookmarks of the given url.

                In the case of getting bookmarks of a url (url is set),
                get_bookmarks() will take *considerably* longer to run
                for pages with lots of bookmarks when setting max_bookmarks
                to a high number or when you completely disable the limit.
                Delicious returns only up to 50 bookmarks per result page,
                so for example retrieving 250 bookmarks requires 5 HTTP
                connections and parsing 5 HTML pages plus wait time between
                queries (to comply with delicious' Terms of Use; see
                also parameter 'sleep_seconds').

                In the case of getting bookmarks of a user (username is set),
                any values greater than 100 will be an order of magnitude slower
                than values less than or equal to 100, because in the latter
                case we use the official JSON feeds (fast!).

            sleep_seconds (optional, default: 1)
                Wait the specified number of seconds between subsequent
                queries in case that there are multiple pages of bookmarks
                for the given url. Must be greater than or equal to 1 to
                comply with delicious' Terms of Use.
                See also parameter 'max_bookmarks'.

        """
        # we must wait at least 1 second between subsequent queries to
        # comply with delicious' Terms of Use
        assert sleep_seconds >= 1

        # url XOR username
        assert bool(username) is not bool(url)

        path = None
        if url:
            m = md5.new(url)
            hash = m.hexdigest()

            # path will change later on if there are multiple pages of boomarks
            # for the given url
            path = "/url/%s" % hash
        elif username:
            # path will change later on if there are multiple pages of boomarks
            # for the given username
            path = "/%s?setcount=100" % username
        else:
            raise Exception('You must specify either url or user.')

        page_index = 1
        bookmarks = []
        while path:
            data = self._query(path)
            path = None
            if data:
                # extract bookmarks for current page
                if url:
                    bookmarks.extend(self._extract_bookmarks_from_url_history(data))
                else:
                    bookmarks.extend(self._extract_bookmarks_from_user_history(data))

                # check if there are more multiple pages of bookmarks for this url
                soup = BeautifulSoup(data)
                paginations = soup.findAll("div", id="pagination")
                if paginations:
                    # find next path
                    nexts = paginations[0].findAll("a", attrs={ "class": "pn next" })
                    if nexts and (max_bookmarks == 0 or len(bookmarks) < max_bookmarks) and len(bookmarks) > 0:
                        # e.g. /url/2bb293d594a93e77d45c2caaf120e1b1?show=all&page=2
                        path = nexts[0]['href']
                        if username:
                            path += "&setcount=100"
                        page_index += 1
                        # wait one second between queries to be compliant with
                        # delicious' Terms of Use
                        time.sleep(sleep_seconds)
        if max_bookmarks > 0:
            return bookmarks[:max_bookmarks]
        else:
            return bookmarks

    def _extract_bookmarks_from_url_history(self, data):
        bookmarks = []
        soup = BeautifulSoup(data)

        bookmark_elements = soup.findAll("div", attrs={"class": re.compile("^bookmark\s*")})
        timestamp = None
        for bookmark_element in bookmark_elements:

            # extract bookmark creation time
            #
            # this timestamp has to "persist" until a new timestamp is
            # found (delicious only provides the creation time data for the
            # first bookmark in the list of bookmarks for a given day
            dategroups = bookmark_element.findAll("div", attrs={"class": "dateGroup"})
            if dategroups:
                spans = dategroups[0].findAll('span')
                if spans:
                    date_str = spans[0].contents[0].strip()
                    timestamp =  datetime.datetime.strptime(date_str, '%d %b %y')

            # extract comments
            comment = u""
            datas = bookmark_element.findAll("div", attrs={"class": "data"})
            if datas:
                divs = datas[0].findAll("div", attrs={"class": "description"})
                if divs:
                    comment = divs[0].contents[0].strip()

            # extract tags
            user_tags = []
            tagdisplays = bookmark_element.findAll("div", attrs={"class": "tagdisplay"})
            if tagdisplays:
                spans = tagdisplays[0].findAll("span", attrs={"class": "tag-chain-item-span"})
                for span in spans:
                    tag = span.contents[0]
                    user_tags.append(tag)

            # extract user information
            metas = bookmark_element.findAll("div", attrs={"class": "meta"})
            if metas:
                links = metas[0].findAll("a", attrs={"class": "user user-tag"})
                if links:
                    user_a = links[0]
                    spans = user_a.findAll('span')
                    if spans:
                        user = spans[0].contents[0]
                    bookmarks.append( (user, user_tags, comment, timestamp) )

        return bookmarks

    def _extract_bookmarks_from_user_history(self, data):
        bookmarks = []
        soup = BeautifulSoup(data)

        ul = soup.find("ul", id="bookmarklist")
        if ul:
            bookmark_elements = ul.findAll("div", attrs={"class": re.compile("^bookmark\s*")})
            timestamp = None
            for bookmark_element in bookmark_elements:

                # extract bookmark creation time
                #
                # this timestamp has to "persist" until a new timestamp is
                # found (delicious only provides the creation time data for the
                # first bookmark in the list of bookmarks for a given day
                dategroups = bookmark_element.findAll("div", attrs={"class": "dateGroup"})
                if dategroups:
                    spans = dategroups[0].findAll('span')
                    if spans:
                        date_str = spans[0].contents[0].strip()
                        timestamp =  datetime.datetime.strptime(date_str, '%d %b %y')

                # extract comments
                comment = u""
                datas = bookmark_element.findAll("div", attrs={"class": "data"})
                if datas:
                    links = datas[0].findAll("a", attrs={"class": "taggedlink"})
                    if links:
                        title = links[0].contents[0].strip()
                        url = links[0]['href']
                    divs = datas[0].findAll("div", attrs={"class": "description"})
                    if divs:
                        comment = divs[0].contents[0].strip()

                # extract tags
                url_tags = []
                tagdisplays = bookmark_element.findAll("div", attrs={"class": "tagdisplay"})
                if tagdisplays:
                    spans = tagdisplays[0].findAll("span", attrs={"class": "tag-chain-item-span"})
                    for span in spans:
                        tag = span.contents[0]
                        url_tags.append(tag)

                bookmarks.append( (url, url_tags, title, comment, timestamp) )

        return bookmarks


    def get_user(self, username, password=None, max_bookmarks=50, sleep_seconds=1):
        """Retrieves a user's bookmarks from delicious.com.

        If a correct username AND password are supplied, a user's *full*
        bookmark collection (which also includes private bookmarks) is
        retrieved. Data communication is encrypted using SSL in this case.

        If no password is supplied, only the most recent public bookmarks
        of the user are extracted from his/her JSON feed (up to 100 bookmarks
        if any). Note that if you want to get the *full* tagging vocabulary
        of the user even if you don't know the password, you can call
        get_tags_of_user() instead.

        This function can be used to backup all of a user's bookmarks if
        called with a username and password.

        Parameters:
            username:
                The delicious.com username.

            password (optional, default: None)
                The user's delicious.com password. If password is set,
                all communication with delicious.com is SSL-encrypted.

            max_bookmarks (optional, default: 50)
                See the documentation of get_bookmarks() for more
                information as get_url() uses get_bookmarks() to
                retrieve a url's bookmarking history.

            sleep_seconds (optional, default: 1)
                See the documentation of get_bookmarks() for more
                information as get_url() uses get_bookmarks() to
                retrieve a url's bookmarking history.

        Returns a DeliciousUser instance.

        """
        assert username
        user = DeliciousUser(username)
        bookmarks = []
        if password:
            # We have username AND password, so we call
            # the official delicious.com API.
            path = "/v1/posts/all"
            data = self._query(path, host="api.del.icio.us", use_ssl=True, user=username, password=password)
            if data:
                soup = BeautifulSoup(data)
                elements = soup.findAll("post")
                for element in elements:
                    url = element["href"]
                    title = element["description"] or u""
                    comment = element["extended"] or u""
                    tags = []
                    if element["tag"]:
                        tags = element["tag"].split()
                    timestamp = datetime.datetime.strptime(element["time"], "%Y-%m-%dT%H:%M:%SZ")
                    bookmarks.append( (url, tags, title, comment, timestamp) )
            user.bookmarks = bookmarks
        else:
            # We have only the username, so we extract data from
            # the user's JSON feed. However, the feed is restricted
            # to the most recent public bookmarks of the user, which
            # is about 100 if any. So if we need more than 100, we start
            # scraping the delicious.com website directly
            if max_bookmarks > 0 and max_bookmarks <= 100:
                path = "/v2/json/%s?count=100" % username
                data = self._query(path, host="feeds.delicious.com", user=username)
                if data:
                    try:
                        posts = simplejson.loads(data)
                    except TypeError:
                        pass

                    url = timestamp = None
                    title = comment = u""
                    tags = []

                    for post in posts:
                        # url
                        try:
                            url = post['u']
                        except KeyError:
                            pass
                        # title
                        try:
                            title = post['d']
                        except KeyError:
                            pass
                        # tags
                        try:
                            tags = post['t']
                        except KeyError:
                            pass
                        if not tags:
                            tags = [u"system:unfiled"]
                        # comment / notes
                        try:
                            timestamp = datetime.datetime.strptime(post['dt'], "%Y-%m-%dT%H:%M:%SZ")
                        except KeyError:
                            pass
                        bookmarks.append( (url, tags, title, comment, timestamp) )
                    user.bookmarks = bookmarks[:max_bookmarks]
            else:
                # TODO: retrieve the first 100 bookmarks via JSON before
                #       falling back to scraping the delicous.com website
                user.bookmarks = self.get_bookmarks(username=username, max_bookmarks=max_bookmarks, sleep_seconds=sleep_seconds)
        return user


    def get_tags_of_user(self, username):
        """
        Retrieves user's public tags and their tag counts from delicious.com.
        The tags represent a user's full public tagging vocabulary.

        DeliciousAPI uses the official JSON feed of the user. We could use
        RSS here, but the JSON feed has proven to be faster in practice.

        Returns a dictionary mapping tags to their tag counts.

        """
        tags = {}
        path = "/v2/json/tags/%s" % username
        data = self._query(path, host="feeds.delicious.com")
        if data:
            try:
                tags = simplejson.loads(data)
            except TypeError:
                pass
        return tags

    def get_number_of_users(self, url):
        """get_number_of_users() is obsolete and has been removed. Please use get_url() instead."""
        reason = "get_number_of_users() is obsolete and has been removed. Please use get_url() instead."
        raise Exception(reason)

    def get_common_tags_of_url(self, url):
        """get_common_tags_of_url() is obsolete and has been removed. Please use get_url() instead."""
        reason = "get_common_tags_of_url() is obsolete and has been removed. Please use get_url() instead."
        raise Exception(reason)

    def _html_escape(self, s):
        """HTML-escape a string or object.

        This converts any non-string objects passed into it to strings
        (actually, using unicode()).  All values returned are
        non-unicode strings (using "&#num;" entities for all non-ASCII
        characters).

        None is treated specially, and returns the empty string.
        """
        if s is None:
            return ''
        if not isinstance(s, basestring):
            if hasattr(s, '__unicode__'):
                s = unicode(s)
            else:
                s = str(s)
        s = cgi.escape(s, True)
        if isinstance(s, unicode):
            s = s.encode('ascii', 'xmlcharrefreplace')
        return s


class DeliciousError(Exception):
    """Used to indicate that an error occurred when trying to access delicious.com via its API."""

class DeliciousWarning(Exception):
    """Used to indicate a warning when trying to access delicious.com via its API.

    Warnings are raised when it is useful to alert the user of some condition
    where that condition doesn't warrant raising an exception and terminating
    the program. For example, we issue a warning when delicious.com returns a
    HTTP status code for redirections (3xx).
    """

class DeliciousThrottleError(DeliciousError):
    """Used to indicate that the client computer (i.e. its IP address) has been temporarily blocked by delicious.com."""
    pass

class DeliciousUnknownError(DeliciousError):
    """Used to indicate that delicious.com returned an (HTTP) error which we don't know how to handle yet."""
    pass

class DeliciousUnauthorizedError(DeliciousError):
    """Used to indicate that delicious.com returned a 401 Unauthorized error.

    Most of the time, the user credentials for acessing restricted (official)
    delicious.com API functions are incorrect.

    """
    pass

class DeliciousNotFoundError(DeliciousError):
    """Used to indicate that delicious.com returned a 404 Not Found error.

    Most of the time, retrying some seconds later fixes the problem
    (because we only query existing pages with this API).

    """
    pass

class Delicious500Error(DeliciousError):
    """Used to indicate that delicious.com returned a 500 error.

    Most of the time, retrying some seconds later fixes the problem
    (because we only query existing pages with this API).

    """
    pass

class DeliciousMovedPermanentlyWarning(DeliciousWarning):
    """Used to indicate that delicious.com returned a 301 Found (Moved Permanently) redirection."""
    pass

class DeliciousMovedTemporarilyWarning(DeliciousWarning):
    """Used to indicate that delicious.com returned a 302 Found (Moved Temporarily) redirection."""
    pass

__all__ = ['DeliciousAPI', 'DeliciousURL', 'DeliciousError', 'DeliciousThrottleError', 'DeliciousUnauthorizedError', 'DeliciousUnknownError', 'DeliciousNotFoundError' , 'Delicious500Error', 'DeliciousMovedTemporarilyWarning']

if __name__ == "__main__":
    d = DeliciousAPI()
    max_bookmarks = 50
    url = 'http://www.michael-noll.com/wiki/Del.icio.us_Python_API'
    print "Retrieving delicious.com information about url"
    print "'%s'" % url
    print "Note: This might take some time..."
    print "========================================================="
    document = d.get_url(url, max_bookmarks=max_bookmarks)
    print document
