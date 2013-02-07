from lwr.lwr_client.transport import Urllib2Transport, PycurlTransport
from tempfile import NamedTemporaryFile


def test_urllib_transports():
    _test_transport(Urllib2Transport())


def test_pycurl_transport():
    _test_transport(PycurlTransport())


def _test_transport(transport):
    ## Testing simple get
    response = transport.execute("http://www.google.com", data=None)
    assert response.find("<title>Google</title>") > 0

    ## Testing writing to output file
    temp_file = NamedTemporaryFile(delete=True)
    output_path = temp_file.name
    temp_file.close()
    response = transport.execute("http://www.google.com", data=None, output_path=output_path)
    assert open(output_path, 'r').read().find("<title>Google</title>") > 0
