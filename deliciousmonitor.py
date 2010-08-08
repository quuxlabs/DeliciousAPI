"""
    A module to monitor a delicious.com bookmark RSS feed and store it with some additional metadata to file.
    
    (c) 2006-2008 Michael G. Noll <http://www.michael-noll.com/>
    
"""
import codecs
import datetime
import os
import sys
import time

try:
    import deliciousapi
except:
    print "ERROR: could not import DeliciousAPI module"
    print
    print "You can download DeliciousAPI from the Python Cheese Shop at"
    print "http://pypi.python.org/pypi/DeliciousAPI"
    print

try:
    import feedparser
except:
    print "ERROR: could not import Universal Feed Parser module"
    print
    print "You can download Universal Feed Parser from the Python Cheese Shop at"
    print "http://pypi.python.org/pypi/FeedParser"
    print
    raise


class DeliciousMonitor(object):
    """Monitors a delicious.com bookmark RSS feed, retrieves metadata for each bookmark and stores it to file.
    
    By default, the delicious.com hotlist (i.e. the front page) is monitored.
    Whenever the monitor discovers a new URL in a bookmark, it retrieves
    some metadata for it from delicious.com (currently, common tags and number
    of bookmarks) and stores this information to file.
    
    Note that URLs which have been processed in previous runs will NOT be
    processed again, i.e. delicious.com metadata will NOT be updated.
    
    """
    
    def __init__(self, rss_url="http://feeds.delicious.com/v2/rss", filename="delicious-monitor.xml", log_filename="delicious-monitor.log", interval=30, verbose=True):
        """
        Parameters:
            rss_url (optional, default: "http://feeds.delicious.com/v2/rss")
                The URL of the RSS feed to monitor.
            
            filename (optional, default: "delicious-monitor.xml")
                The name of the file to which metadata about the RSS feed will be stored.
            
            log_filename (optional, default: "delicious-monitor.log")
                The name of the log file, which is used to identify "new" entries in the RSS feed.
            
            interval (optional, default: 30)
                Time between monitor runs in minutes.
            
            verbose (optional, default: True)
                Whether to print non-critical processing information to STDOUT or not.
                
        """
        self.rss_url = rss_url
        self._delicious = deliciousapi.DeliciousAPI()
        self.filename = filename
        self.log_filename = log_filename
        self.interval = interval
        self.verbose = verbose
        self.urls = []
        # ensure that the name of the output file and log file is not None etc.
        assert self.filename
        assert self.log_filename
        
    def run(self):
        """Start the monitor."""
        while True:
            time_before_run = datetime.datetime.now()
            
            # do the actual monitoring work
            if self.verbose:
                print "[MONITOR] Starting monitor run - %s" % time_before_run.strftime("%Y-%m-%d @ %H:%M:%S")
            self.monitor()
            time_after_run = datetime.datetime.now()

            # calculate the number of seconds to wait until the next run
            interval = datetime.timedelta(seconds=60*self.interval)
            next_run_time = time_before_run + interval
            elapsed = time_after_run - time_before_run
            if interval >= elapsed:
                wait_seconds = (interval - elapsed).seconds
            else:
                # the run took longer than our interval time between runs;
                # in this case, we continue immediately but will still wait
                # three seconds in order not to stress delicious.com too much
                wait_seconds = 3
                next_run_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_seconds)
            
            # sleep until the next run
            if self.verbose:
                print "[MONITOR] Next monitor run on %s (sleeping for %s seconds)" % (next_run_time.strftime("%Y-%m-%d @ %H:%M:%S"), wait_seconds)
            time.sleep(wait_seconds)
        
    def monitor(self):
        """Monitors an RSS feed."""
        
        # download and parse RSS feed
        f = feedparser.parse(self.rss_url)
        
        output_file = codecs.open(self.filename, "a", "utf8")
        log_file = None
        
        if os.access(self.log_filename, os.F_OK):
            if self.verbose:
                print "[MONITOR] Log file found. Trying to resume...",
            try:
                # read in previous log data for resuming
                log_file = open(self.log_filename, 'r')
                # remove leading and trailing whitespace if any (incl. newlines)
                self.urls = [line.strip() for line in log_file.readlines()]
                log_file.close()
                if self.verbose:
                    print "done"
            except IOError:
                # most probably, the log file does not exist (yet)
                if self.verbose:
                    print "failed"
        else:
            # log file does not exist, so there isn't any resume data
            # to read in
            pass

        try:
            # now open it for writing (i.e., appending) and logging
            if self.verbose:
                print "[MONITOR] Open log file for appending...",
            log_file = open(self.log_filename, 'a')
            if self.verbose:
                print "done"
        except IOError:
            if self.verbose:
                print "failed"
            print "[MONITOR] ERROR: could not open log file for appending"
            self._cleanup()
            return
        
        # get only new entries
        new_entries = []
        for entry in f.entries:
            new_entries = [entry for entry in f.entries if entry.link not in self.urls]
        
        if self.verbose:
            print "[MONITOR] Found %s new entries" % len(new_entries)
        
        # query metadata about each entry from delicious.com
        for index, entry in enumerate(new_entries):
            url = entry.link
            
            if self.verbose:
                print "[MONITOR] Processing entry #%s: '%s'" % (index + 1, url),
            try:
                time.sleep(1) # be nice and wait 1 sec between connects to delicious.com
                document = self._delicious.get_url(url)
            except (deliciousapi.DeliciousError,), error_string:
                if self.verbose:
                    print "failed"
                print "[MONITOR] ERROR: %s" % error_string
                # clean up
                output_file.close()
                log_file.close()
                return
            
            if self.verbose:
                print "done"
            
            # update log file
            log_file.write("%s\n" % url)
            # update output file
            output_file.write('<document url="%s" users="%s" top_tags="%s">\n' % (url, document.total_bookmarks, len(document.top_tags)))
            for tag, count in document.top_tags:
                output_file.write('    <top_tag name="%s" count="%s" />\n' % (tag, count))
            output_file.write('</document>\n')
            output_file.flush()
        
        # clean up
        output_file.close()
        log_file.close()
        
        
if __name__ == "__main__":
    monitor = DeliciousMonitor(interval=30)
    monitor.run()
