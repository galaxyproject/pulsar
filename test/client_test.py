import urllib
import tempfile
import os

from lwr.client import Client

class FakeResponse(object):
    """ Object meant to simulate a Response object as returned by
    urllib.open """

    def __init__(self, body):
        self.body = body
        self.first_read = True

    def read(self, bytes = 1024):
        if self.first_read:
            result = self.body
        else:
            result = ""
        self.first_read = False
        return result

class TestClient(Client):
    """ A dervative of the Client class that replaces the url_open
    method so that requests can be inspected and responses faked."""

    def __init__(self): 
        Client.__init__(self, "http://test:803/", "543")

    def expect_open(self, checker, response):
        self.checker = checker
        self.response = response

    def url_open(self, request, data):
        self.checker(request, data)
        return FakeResponse(self.response)

class RequestChecker(object):
    """ Class that tests request objects produced by the Client class.
    """
    def __init__(self, action, args = {}, data = None):        
        args['job_id'] = "543"
        self.action = action
        self.expected_args = args
        self.data = data
        self.called = False


    def check_url(self, opened_url):
        expected_url_prefix = "http://test:803/%s?" % self.action
        assert opened_url.startswith(expected_url_prefix)
        url_suffix = opened_url[len(expected_url_prefix):]
        actual_args = dict([key_val_combo.split("=") for key_val_combo in url_suffix.split("&")])
        statement = "Expected args %s, obtained %s" % (self.expected_args, actual_args)
        assert self.expected_args == actual_args, statement

    def check_data(self, data):
        if data == None:
            assert self.data == None
        else:
            assert data.read(1024) == self.data
        

    def __call__(self, request, data = None):
        self.called = True
        self.check_url(request.get_full_url())
        self.check_data(data)

    def assert_called(self):
        assert self.called

def test_setup():
    """ Test the setup method of Client """
    client = TestClient()
    request_checker = RequestChecker("setup")
    response_json = '{"working_directory":"C:\\\\home\\\\dir","outputs_directory" : "C:\\\\outputs","path_separator" : "\\\\"}'
    client.expect_open(request_checker, response_json)
    setup_response = client.setup()
    request_checker.assert_called()
    assert setup_response['working_directory'] == "C:\\home\\dir"
    assert setup_response['outputs_directory'] == "C:\\outputs"
    assert setup_response['path_separator'] == '\\'
    
def test_launch():
    """ Test the launch method of client. """
    client = TestClient()
    request_checker = RequestChecker("launch", {"command_line" : "python" })
    client.expect_open(request_checker, 'OK')
    client.launch("python")
    request_checker.assert_called()

def __test_upload(upload_type):
    client = TestClient()

    #temp_file = tempfile.NamedTemporaryFile()
    (temp_fileno, temp_file_path) = tempfile.mkstemp()
    temp_file = os.fdopen(temp_fileno, 'w')
    try:
        temp_file.write("Hello World!")
    finally:
        temp_file.close()
    request_checker = RequestChecker("upload_%s" % upload_type, {"name" : os.path.basename(temp_file_path)}, "Hello World!")
    client.expect_open(request_checker, '{"path" : "C:\\\\tools\\\\foo"}')

    if(upload_type == 'tool_file'):
        upload_result = client.upload_tool_file(temp_file_path)
    else:
        upload_result = client.upload_input(temp_file_path)

    request_checker.assert_called()
    assert upload_result["path"] == "C:\\tools\\foo"

def test_upload_tool():
    __test_upload("tool_file")
    
def test_upload_input():
    __test_upload("input")

def test_download_output():
    """ Test the download output method of Client. """
    client = TestClient()
    temp_file = tempfile.NamedTemporaryFile()
    temp_file.close()
    request_checker = RequestChecker("download_output", {"name" : os.path.basename(temp_file.name)})
    client.expect_open(request_checker, "test output contents")
    client.download_output(temp_file.name)
    
    contents = open(temp_file.name, "r")
    try:
        assert contents.read(1024) == "test output contents"
    finally:
        contents.close()
    
def test_wait():
    client = TestClient()
    #request_checker = RequestChecker("check_complete")
    #client.expect_open(request_checker, '{"complete": "false"}')
    #wait_response = client.wait()
    #request_checker.assert_called()

    request_checker = RequestChecker("check_complete")
    client.expect_open(request_checker, '{"complete": "true", "stdout" : "output"}')
    wait_response = client.wait()
    request_checker.assert_called()
    assert wait_response['stdout'] == "output"

def test_kill():
    client = TestClient()
    request_checker = RequestChecker("kill")
    client.expect_open(request_checker, 'OK')
    client.kill()
    request_checker.assert_called()

def test_clean():
    client = TestClient()
    request_checker = RequestChecker("clean")
    client.expect_open(request_checker, 'OK')
    client.clean()
    request_checker.assert_called()
