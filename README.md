DeliciousAPI
============

Unofficial Python API for retrieving data from Delicious.com

Features
--------

This Python module provides the following features plus some more:

* Retrieving a URL's full public bookmarking history including users who bookmarked the URL including tags used for such bookmarks and the creation time of the bookmark (up to YYYY-MM-DD granularity)
* Top tags (up to a maximum of 10) including tag count title as stored on Delicious.com
* Total number of bookmarks/users for this URL at Delicious.com retrieving a user's full bookmark collection, including any private bookmarks if you know the corresponding password
* Retrieving a user's full public tagging vocabulary, i.e. tags and tag counts
* Retrieving a user's network information (network members and network fans)
* HTTP proxy support

The official Delicious.com API and the JSON/RSS feeds do not provide all the functionality mentioned above, and in such cases this module will query the Delicious.com website directly and extract the required information by parsing the HTML code of the resulting Web pages (a kind of poor man's web mining). The module is able to detect IP throttling, which is employed by Delicious.com to temporarily block abusive HTTP request behavior, and will raise a custom Python error to indicate that. Please be a nice netizen and do not stress the Delicious.com service more than necessary.  

Installation
------------

You can now download and install DeliciousAPI from Python Package Index (aka Python Cheese Shop) (includes only deliciousapi.py) via setuptools/easy_install. Just run

    $ easy_install DeliciousAPI

After installation, a simple import deliciousapi in your Python scripts will do the trick.

An alternative installation method is downloading the code straight from the git repository.

Updates
-------

If you used setuptools/easy_install for installation, you can update DeliciousAPI via

    $ easy_install -U DeliciousAPI

Alternatively, if you downladed the code from the git repository, simply pull the latest changes.

Usage
-----

For now, please refer to the documentation available at [http://www.michael-noll.com/wiki/Del.icio.us_Python_API](http://www.michael-noll.com/wiki/Del.icio.us_Python_API).

Important
---------

It is strongly advised that you read the Delicious.com Terms of Use prior to using this Python module. In particular, read section 5 'Intellectual Property'.

License
-------

The code is licensed to you under version 2 of the GNU General Public License.

Copyright
---------

Copyright 2006-2010 Michael G. Noll <http://www.michael-noll.com/>

