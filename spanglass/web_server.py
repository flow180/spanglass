#! /usr/bin/env python

"""
SimpleHTTPServer with 206 support
Adapted from here: https://gist.github.com/pankajp/280596a5dabaeeceaaaa/
Changes made are mostly to pass linting
"""

# Standard library imports.
from SocketServer import ThreadingMixIn
import BaseHTTPServer
import SimpleHTTPServer
import os
import urlparse
import re


class RequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    """ Handler to handle POST requests for actions.
    """
    clean_urls = False
    serve_path = None
    range_from = None
    range_to = None

    def do_GET(self):
        """ Overridden to handle HTTP Range requests. """
        if os.path.splitext(self.path)[1] == '' and self.clean_urls and not os.path.exists(self.translate_path(self.path)) and os.path.exists(self.translate_path(self.path) + '.html'):
            self.path = self.path + '.html'
        self.range_from, self.range_to = self._get_range_header()
        if self.range_from is None:
            # nothing to do here
            return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
        file_handle = self.send_range_head()
        if file_handle:
            self.copy_file_range(file_handle, self.wfile)
            file_handle.close()

    def copy_file_range(self, in_file, out_file):
        """ Copy only the range in self.range_from/to. """
        in_file.seek(self.range_from)
        # Add 1 because the range is inclusive
        left_to_copy = 1 + self.range_to - self.range_from
        buf_length = 64 * 1024
        bytes_copied = 0
        while bytes_copied < left_to_copy:
            read_buf = in_file.read(min(buf_length, left_to_copy))
            if len(read_buf) == 0:
                break
            out_file.write(read_buf)
            bytes_copied += len(read_buf)
        return bytes_copied

    def send_range_head(self):
        """Common code for GET and HEAD commands.
        This sends the response code and MIME headers.
        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.
        """
        path = self.translate_path(self.path)
        file_handle = None
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
        ctype = self.guess_type(path)
        if not os.path.exists(path) and path.endswith('/data'):
            # stupid grits
            if os.path.exists(path[:-5]):
                path = path[:-5]
        if os.path.splitext(path)[1] == '' and self.clean_urls and not os.path.exists(path) and os.path.exists(path + '.html'):
            path = path + '.html'
        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            file_handle = open(path, 'rb')
        except IOError:
            self.send_error(404, "File not found")
            return None

        if self.range_from is None:
            self.send_response(200)
        else:
            self.send_response(206)

        self.send_header("Content-type", ctype)
        file_stat = os.fstat(file_handle.fileno())
        file_size = file_stat.st_size
        if self.range_from is not None:
            if self.range_to is None or self.range_to >= file_size:
                self.range_to = file_size - 1
            self.send_header("Content-Range",
                             "bytes %d-%d/%d" % (self.range_from,
                                                 self.range_to,
                                                 file_size))
            # Add 1 because ranges are inclusive
            self.send_header("Content-Length",
                             (1 + self.range_to - self.range_from))
        else:
            self.send_header("Content-Length", str(file_size))
        self.send_header(
            "Last-Modified", self.date_time_string(file_stat.st_mtime))
        self.end_headers()
        return file_handle

    def translate_path(self, path):
        """ Override to handle redirects.
        """
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        path = os.path.normpath(urlparse.unquote(path))
        words = path.split('/')
        path = self.serve_path
        for word in words:
            word = os.path.splitdrive(word)[1]
            word = os.path.split(word)[1]
            if word in (os.curdir, os.pardir):
                continue
            path = os.path.join(path, word)
        return path

    # Private interface ######################################################

    def _get_range_header(self):
        """ Returns request Range start and end if specified.
        If Range header is not specified returns (None, None)
        """
        range_header = self.headers.getheader("Range")
        if range_header is None:
            return (None, None)
        if not range_header.startswith("bytes="):
            return (None, None)
        regex = re.compile(r"^bytes=(\d+)\-(\d+)?")
        rangething = regex.search(range_header)
        if rangething:
            from_val = int(rangething.group(1))
            if rangething.group(2) is not None:
                return (from_val, int(rangething.group(2)))
            else:
                return (from_val, None)
        else:
            return (None, None)


class ThreadingHTTPServer(ThreadingMixIn, BaseHTTPServer.HTTPServer):
    """ Combine ThreadingMixin and BaseHTTPServer """

    def __init__(self, port, serve_path='.', clean_urls=False):
        handler = RequestHandler
        handler.serve_path = serve_path
        handler.clean_urls = clean_urls
        if clean_urls: 
             handler.extensions_map[''] = 'text/html'
        BaseHTTPServer.HTTPServer.__init__(self, ("", port), handler)
