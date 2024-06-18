import logging

try:
    from urllib2 import urlopen
except ImportError:
    from urllib.request import urlopen
try:
    from urllib2 import Request
except ImportError:
    from urllib.request import Request

try:
    import poster
except ImportError:
    poster = None

POSTER_UNAVAILABLE_MESSAGE = "Pulsar configured to use poster module - but it is unavailable. Please install poster."

log = logging.getLogger(__name__)


if poster is not None:
    poster.streaminghttp.register_openers()


def post_file(url, path):
    __ensure_poster()
    try:
        with open(path, "rb") as fh:
            datagen, headers = poster.encode.multipart_encode({"file": fh})
            request = Request(url, datagen, headers)
            return urlopen(request).read()
    except Exception:
        log.exception("Problem with poster post of [%s]" % path)
        raise


def get_file(url, path):
    __ensure_poster()
    request = Request(url=url)
    response = urlopen(request)
    with open(path, 'wb') as output:
        while True:
            buffer = response.read(1024)
            if not buffer:
                break
            output.write(buffer)


def __ensure_poster():
    if poster is None:
        raise ImportError(POSTER_UNAVAILABLE_MESSAGE)
