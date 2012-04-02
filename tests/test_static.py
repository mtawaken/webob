from os.path import getmtime
import tempfile
from time import gmtime
import os
import shutil
import unittest

from webob import static
from webob.compat import bytes_
from webob.request import Request, environ_from_url
from webob.response import Response


def get_response(app, path='/', **req_kw):
    """Convenient function to query an application"""
    req = Request(environ_from_url(path), **req_kw)
    return req.get_response(app)


def create_file(content, *paths):
    """Convenient function to create a new file with some content"""
    path = os.path.join(*paths)
    with open(path, 'wb') as fp:
        fp.write(bytes_(content))
    return path


class TestFileApp(unittest.TestCase):
    def setUp(self):
        fp = tempfile.NamedTemporaryFile(suffix=".py", delete=False)
        self.tempfile = fp.name
        fp.write(b"import this\n")
        fp.close()

    def tearDown(self):
        os.unlink(self.tempfile)

    def test_fileapp(self):
        app = static.FileApp(self.tempfile)
        resp1 = get_response(app)
        self.assertEqual(resp1.content_type, 'text/x-python')
        self.assertEqual(resp1.charset, 'UTF-8')
        self.assertEqual(resp1.last_modified.timetuple(), gmtime(getmtime(self.tempfile)))

        resp2 = get_response(app)
        self.assertEqual(resp2.content_type, 'text/x-python')
        self.assertEqual(resp2.last_modified.timetuple(), gmtime(getmtime(self.tempfile)))

        resp3 = get_response(app, range=(7, 11))
        self.assertEqual(resp3.status_int, 206)
        self.assertEqual(tuple(resp3.content_range)[:2], (7, 11))
        self.assertEqual(resp3.last_modified.timetuple(), gmtime(getmtime(self.tempfile)))
        self.assertEqual(resp3.body, bytes_('this'))

    def test_unexisting_file(self):
        app = static.FileApp('/tmp/this/doesnt/exist')
        self.assertEqual(404, get_response(app).status_int)

    def test_allowed_methods(self):
        app = static.FileApp(self.tempfile)

        # Alias
        resp = lambda method: get_response(app, method=method)

        self.assertEqual(200, resp(method='GET').status_int)
        self.assertEqual(200, resp(method='HEAD').status_int)
        self.assertEqual(405, resp(method='POST').status_int)
        # Actually any other method is not allowed
        self.assertEqual(405, resp(method='xxx').status_int)

    def test_exception_while_opening_file(self):
        # Mock the built-in ``open()`` function to allow finner control about
        # what we are testing.
        def open_ioerror(*args, **kwargs):
            raise IOError()

        def open_oserror(*args, **kwargs):
            raise OSError()

        app = static.FileApp(self.tempfile)
        old_open = __builtins__['open']

        try:
            __builtins__['open'] = open_ioerror
            self.assertEqual(403, get_response(app).status_int)

            __builtins__['open'] = open_oserror
            self.assertEqual(403, get_response(app).status_int)
        finally:
            __builtins__['open'] = old_open


class TestFileIter(unittest.TestCase):
    def test_empty_file(self):
        fp = tempfile.NamedTemporaryFile()
        fi = static.FileIter(fp)
        self.assertRaises(StopIteration, next, iter(fi))


class TestDirectoryApp(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_empty_directory(self):
        app = static.DirectoryApp(self.test_dir)
        self.assertEqual(404, get_response(app).status_int)
        self.assertEqual(404, get_response(app, '/foo').status_int)

    def test_serve_file(self):
        app = static.DirectoryApp(self.test_dir)
        create_file('abcde', self.test_dir, 'bar')
        self.assertEqual(404, get_response(app).status_int)
        self.assertEqual(404, get_response(app, '/foo').status_int)

        resp = get_response(app, '/bar')
        self.assertEqual(200, resp.status_int)
        self.assertEqual(bytes_('abcde'), resp.body)

    def test_dont_serve_file_in_parent_directory(self):
        # We'll have:
        #   /TEST_DIR/
        #   /TEST_DIR/bar
        #   /TEST_DIR/foo/   <- serve this directory
        create_file('abcde', self.test_dir, 'bar')
        serve_path = os.path.join(self.test_dir, 'foo')
        os.mkdir(serve_path)
        app = static.DirectoryApp(serve_path)

        # The file exists, but is outside the served dir.
        self.assertEqual(403, get_response(app, '/../bar').status_int)

    def test_file_app_arguments(self):
        app = static.DirectoryApp(self.test_dir, content_type='xxx/yyy')
        create_file('abcde', self.test_dir, 'bar')

        resp = get_response(app, '/bar')
        self.assertEqual(200, resp.status_int)
        self.assertEqual('xxx/yyy', resp.content_type)

    def test_file_app_factory(self):
        def make_fileapp(*args, **kwargs):
            make_fileapp.called = True
            return Response()
        make_fileapp.called = False

        app = static.DirectoryApp(self.test_dir)
        app.make_fileapp = make_fileapp
        create_file('abcde', self.test_dir, 'bar')

        get_response(app, '/bar')
        self.assertTrue(make_fileapp.called)

    def test_must_serve_directory(self):
        serve_path = create_file('abcde', self.test_dir, 'bar')
        self.assertRaises(AssertionError, static.DirectoryApp, serve_path)
