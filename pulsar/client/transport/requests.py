import logging

import requests

try:
    import requests_toolbelt
except ImportError:
    requests_toolbelt = None  # type: ignore


log = logging.getLogger(__name__)


def post_file(url, path):
    with open(path, "rb") as f:
        if requests_toolbelt is not None:
            # Streaming multipart upload — avoids loading the whole file into memory.
            m = requests_toolbelt.MultipartEncoder(fields={"file": ("filename", f)})
            response = requests.post(url, data=m, headers={"Content-Type": m.content_type})
        else:
            log.warning(
                "Posting %s without requests_toolbelt: the entire file will be loaded into memory. "
                "Install requests_toolbelt (or pycurl, and use the curl transport) for streaming uploads.",
                path,
            )
            response = requests.post(url, files={'file': f})
        with response:
            response.raise_for_status()


def get_file(url, path):
    with requests.get(url, stream=True) as response:
        response.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    f.flush()
