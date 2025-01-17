# -*- coding: utf-8 -*-
#
# Copyright © 2014-2020  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions
# of the GNU General Public License v.2, or (at your option) any later
# version.  This program is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY expressed or implied, including the
# implied warranties of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.  You
# should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# Any Red Hat trademarks that are incorporated in the source
# code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission
# of Red Hat, Inc.
#
"""
Unit tests for the anitya.lib.backends module.
"""
from __future__ import absolute_import, unicode_literals

import re
import unittest
import urllib.request as urllib
from urllib.error import URLError

import arrow
import mock

import anitya
from anitya.config import config
from anitya.lib import backends
from anitya.lib.exceptions import AnityaPluginException
from anitya.tests.base import AnityaTestCase


class BaseBackendTests(AnityaTestCase):
    def setUp(self):
        super(BaseBackendTests, self).setUp()
        self.backend = backends.BaseBackend()
        self.headers = {
            "User-Agent": "Anitya {0} at release-monitoring.org".format(
                anitya.app.__version__
            ),
            "From": config.get("ADMIN_EMAIL"),
            "If-modified-since": "Thu, 01 Jan 1970 00:00:00 GMT",
        }

    @mock.patch("anitya.lib.backends.http_session")
    def test_call_http_url(self, mock_http_session):
        """Assert HTTP urls are handled by requests"""
        url = "https://www.example.com/"
        self.backend.call_url(url)

        mock_http_session.get.assert_called_once_with(
            url, headers=self.headers, timeout=60, verify=True
        )

    @mock.patch("anitya.lib.backends.requests.Session")
    def test_call_insecure_http_url(self, mock_session):
        """Assert HTTP urls are handled by requests"""
        url = "https://www.example.com/"
        self.backend.call_url(url, insecure=True)

        insecure_session = mock_session.return_value.__enter__.return_value
        insecure_session.get.assert_called_once_with(
            url, headers=self.headers, timeout=60, verify=False
        )

    @mock.patch("urllib.request.urlopen")
    def test_call_ftp_url(self, mock_urllib):
        """Assert FTP urls are handled by requests"""
        url = "ftp://ftp.heanet.ie/debian/"
        req_exp = urllib.Request(url)
        req_exp.add_header("User-Agent", self.headers["User-Agent"])
        req_exp.add_header("From", self.headers["From"])
        self.backend.call_url(url)

        mock_urllib.assert_called_once_with(mock.ANY)

        args, kwargs = mock_urllib.call_args
        req = args[0]

        self.assertEqual(req_exp.get_full_url(), req.get_full_url())
        self.assertEqual(req_exp.header_items(), req.header_items())

    @mock.patch("urllib.request.urlopen")
    def test_call_ftp_url_decode(self, mock_urlopen):
        """Assert decoding is working"""
        url = "ftp://ftp.heanet.ie/debian/"
        exp_resp = "drwxr-xr-x  9 ftp  ftp  4096 Aug 23 09:02 debian\r\n"
        mc = mock.Mock()
        mc.read.return_value = b"drwxr-xr-x  9 ftp  ftp  4096 Aug 23 09:02 debian\r\n"
        mock_urlopen.return_value = mc
        resp = self.backend.call_url(url)

        self.assertEqual(resp, exp_resp)

    @mock.patch("urllib.request.urlopen")
    def test_call_ftp_url_decode_not_utf(self, mock_urlopen):
        """Assert decoding is working"""
        url = "ftp://ftp.heanet.ie/debian/"
        mc = mock.Mock()
        mc.read.return_value = b"\x80\x81"
        mock_urlopen.return_value = mc

        self.assertRaises(AnityaPluginException, self.backend.call_url, url)

    @mock.patch("urllib.request.urlopen")
    def test_call_ftp_url_Exceptions(self, mock_urllib):
        """Assert FTP urls are handled by requests"""
        mock_urllib.side_effect = URLError(mock.Mock("not_found"))
        url = "ftp://example.com"

        self.assertRaises(AnityaPluginException, self.backend.call_url, url)

    def test_expand_subdirs(self):
        """Assert expanding subdirs"""
        exp = "http://ftp.fi.muni.cz/pub/linux/fedora/linux/"
        url = self.backend.expand_subdirs("http://ftp.fi.muni.cz/pub/linux/fedora/*/")

        self.assertEqual(exp, url)

    @mock.patch(
        "anitya.lib.backends.BaseBackend.call_url",
        return_value="drwxr-xr-x  9 ftp  ftp  4096 Aug 23 09:02 debian\r\n",
    )
    def test_expand_subdirs_ftp(self, mock_call_url):
        """Assert expanding subdirs"""
        exp = "ftp://ftp.heanet.ie/debian/"
        url = self.backend.expand_subdirs("ftp://ftp.heanet.ie/deb*/")

        self.assertEqual(exp, url)

    @mock.patch("anitya.lib.backends.http_session")
    def test_call_url_last_change(self, mock_http_session):
        url = "https://www.example.com/"
        exp_headers = self.headers.copy()
        time = arrow.utcnow()
        exp_headers["If-modified-since"] = (
            time.format("ddd, DD MMM YYYY HH:mm:ss") + " GMT"
        )
        self.backend.call_url(url, last_change=time)

        mock_http_session.get.assert_called_once_with(
            url, headers=exp_headers, timeout=60, verify=True
        )


class GetVersionsByRegexTests(unittest.TestCase):
    """
    Unit tests for anitya.lib.backends.get_versions_by_regex
    """

    @mock.patch("anitya.lib.backends.BaseBackend.call_url")
    def test_get_versions_by_regex_not_modified(self, mock_call_url):
        """Assert that not modified response is handled correctly."""
        mock_response = mock.Mock(spec=object)
        mock_response.status_code = 304
        mock_call_url.return_value = mock_response
        mock_project = mock.Mock()
        mock_project.get_time_last_created_version = mock.MagicMock(return_value=None)
        versions = backends.get_versions_by_regex("url", "regex", mock_project)

        self.assertEqual(versions, [])

    @mock.patch("anitya.lib.backends.BaseBackend.call_url")
    def test_get_versions_by_regex_string_response(self, mock_call_url):
        """Assert that string response is handled correctly."""
        mock_call_url.return_value = ""
        mock_project = mock.Mock()

        self.assertRaises(
            AnityaPluginException,
            backends.get_versions_by_regex,
            "url",
            "regex",
            mock_project,
        )


class GetVersionsByRegexTextTests(unittest.TestCase):
    """
    Unit tests for anitya.lib.backends.get_versions_by_regex_text
    """

    def test_get_versions_by_regex_for_text(self):
        """Assert finding versions with a simple regex in text works"""
        text = """
        some release: 0.0.1
        some other release: 0.0.2
        The best release: 1.0.0
        """
        regex = r"\d\.\d\.\d"
        mock_project = mock.Mock(version_prefix="", version_filter=None)
        versions = backends.get_versions_by_regex_for_text(
            text, "url", regex, mock_project
        )
        self.assertEqual(sorted(["0.0.1", "0.0.2", "1.0.0"]), sorted(versions))

    def test_get_versions_by_regex_for_text_tuples(self):
        """Assert regex that result in tuples are joined into a string"""
        text = """
        some release: 0.0.1
        some other release: 0.0.2
        The best release: 1.0.0
        """
        regex = r"(\d)\.(\d)\.(\d)"
        mock_project = mock.Mock(version_prefix="", version_filter=None)
        versions = backends.get_versions_by_regex_for_text(
            text, "url", regex, mock_project
        )
        self.assertEqual(sorted(["0.0.1", "0.0.2", "1.0.0"]), sorted(versions))
        # Demonstrate that the regex does result in an iterable
        self.assertEqual(3, len(re.findall(regex, "0.0.1")[0]))

    def test_get_versions_by_regex_for_text_no_versions(self):
        """Assert an exception is raised if no matches are found"""
        text = "This text doesn't have a release!"
        regex = r"(\d)\.(\d)\.(\d)"
        mock_project = mock.Mock(version_prefix="")
        self.assertRaises(
            AnityaPluginException,
            backends.get_versions_by_regex_for_text,
            text,
            "url",
            regex,
            mock_project,
        )


class FilterVersionsTests(unittest.TestCase):
    """
    Unit tests for anitya.lib.backends.BaseBackend.filter_versions
    """

    def test_filter_versions_match(self):
        """
        Assert that versions get filtered correctly.
        """
        versions = ["1.0.0", "1.0.0-alpha", "1.0.0-beta"]
        filter_str = "alpha;beta"

        filtered_versions = backends.BaseBackend.filter_versions(versions, filter_str)

        self.assertEqual(filtered_versions, ["1.0.0"])

    def test_filter_versions_no_match(self):
        """
        Assert that versions are not filtered if no filter is matched.
        """
        versions = ["1.0.0", "1.0.0-alpha", "1.0.0-beta"]
        filter_str = "gamma"

        filtered_versions = backends.BaseBackend.filter_versions(versions, filter_str)

        self.assertEqual(filtered_versions, versions)

    def test_filter_versions_empty_filter(self):
        """
        Assert that versions are not filtered if no filter is specified.
        """
        versions = ["1.0.0", "1.0.0-alpha", "1.0.0-beta"]
        filter_str = ""

        filtered_versions = backends.BaseBackend.filter_versions(versions, filter_str)

        self.assertEqual(filtered_versions, versions)


if __name__ == "__main__":
    unittest.main()
