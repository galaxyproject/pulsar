from cStringIO import StringIO
from pycurl import Curl
from os.path import getsize


class PycurlTransport(object):

    def execute(self, url, data=None, input_path=None, output_path=None):
        buf = self._open_output(output_path)
        try:
            c = Curl()
            c.setopt(c.URL, url)
            c.setopt(c.WRITEFUNCTION, buf.write)
            if input_path:
                c.setopt(c.UPLOAD, 1)
                c.setopt(c.READFUNCTION, open(input_path, 'rb').read)
                filesize = getsize(input_path)
                c.setopt(c.INFILESIZE, filesize)
            if data:
                c.setopt(c.POST, 1)
                c.setopt(c.POSTFIELDS, data)
            c.perform()
            if not output_path:
                return buf.getvalue()
        finally:
            buf.close()

    def _open_output(self, output_path):
        return open(output_path, 'wb') if output_path else StringIO()
