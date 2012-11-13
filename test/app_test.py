from webtest import TestApp
from webob import Request, Response
from lwr.app import app_factory
from lwr.manager import Manager
import tempfile
import os
import shutil
import simplejson
import urllib
import time

def test_app():
    """ Tests all of the app controller methods. These tests should be
    compartmentalized. Also these methods should be made to not retest
    the behavior of the associated Manager class. """

    staging_directory = tempfile.mkdtemp()
    try:
        app = app_factory({}, staging_directory = staging_directory)
        test_app = TestApp(app)
        
        job_id = "12345"

        setup_response = test_app.get("/setup?job_id=%s" % job_id)
        setup_config = simplejson.loads(setup_response.body)
        assert setup_config["working_directory"].startswith(staging_directory)
        outputs_directory = setup_config["outputs_directory"]
        assert outputs_directory.startswith(staging_directory)
        assert setup_config["path_separator"] == os.sep

        def test_upload(upload_type):
            url = "/upload_%s?job_id=%s&name=input1" % (upload_type, job_id)
            upload_input_response = test_app.post(url, "Test Contents")
            upload_input_config = simplejson.loads(upload_input_response.body)
            staged_input_path = upload_input_config["path"]
            staged_input = open(staged_input_path, "r")
            try:
                assert staged_input.read() == "Test Contents"
            finally:
                staged_input.close()            
        test_upload("input")
        test_upload("tool_file")

        test_output = open(os.path.join(outputs_directory, "test_output"), "w")
        try:
            test_output.write("Hello World!")
        finally:
            test_output.close()
        download_response = test_app.get("/download_output?job_id=%s&name=test_output" % job_id)
        assert download_response.body == "Hello World!"

        command_line = urllib.quote("""python -c "import sys; sys.stdout.write('test_out')" """)
        launch_response = test_app.get("/launch?job_id=%s&command_line=%s" % (job_id, command_line))
        assert launch_response.body == 'OK'
        
        time.sleep(5)

        check_response = test_app.get("/check_complete?job_id=%s" % job_id)
        check_config = simplejson.loads(check_response.body)
        assert check_config['returncode'] == 0
        assert check_config['stdout'] == "test_out"
        assert check_config['stderr'] == ""
        
        kill_response = test_app.get("/kill?job_id=%s" % job_id)
        assert kill_response.body == 'OK'

        clean_response = test_app.get("/clean?job_id=%s" % job_id)
        assert clean_response.body == 'OK'
        assert os.listdir(staging_directory) == []

    finally:
        try:
            app.shutdown()
        except:
            pass
        shutil.rmtree(staging_directory)
