from lwr.lwr_client.transport.standard import Urllib2Transport
from lwr.lwr_client.transport.curl import PycurlTransport
from lwr.lwr_client.transport import get_transport
from tempfile import NamedTemporaryFile


def test_urllib_transports():
    _test_transport(Urllib2Transport())


def test_pycurl_transport():
    _test_transport(PycurlTransport())


def _test_transport(transport):
    # Testing simple get
    response = transport.execute(u"http://www.google.com", data=None)
    assert response.find("<title>Google</title>") > 0

    # Testing writing to output file
    temp_file = NamedTemporaryFile(delete=True)
    output_path = temp_file.name
    temp_file.close()
    response = transport.execute(u"http://www.google.com", data=None, output_path=output_path)
    assert open(output_path, 'r').read().find("<title>Google</title>") > 0


def test_get_transport():
    assert type(get_transport(None, FakeOsModule("1"))) == PycurlTransport
    assert type(get_transport(None, FakeOsModule("TRUE"))) == PycurlTransport
    assert type(get_transport(None, FakeOsModule("0"))) == Urllib2Transport
    assert type(get_transport('urllib', FakeOsModule("TRUE"))) == Urllib2Transport
    assert type(get_transport('curl', FakeOsModule("TRUE"))) == PycurlTransport


class FakeOsModule(object):

    def __init__(self, env_val):
        self.env_val = env_val

    def getenv(self, key, default):
        return self.env_val
