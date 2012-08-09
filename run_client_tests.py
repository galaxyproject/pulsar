import shutil
import tempfile
import os
import optparse
import traceback

from lwr.client import Client

def main():
    """ Exercises a running lwr server application with the lwr client. """
    parser = optparse.OptionParser()
    parser.add_option('--url', dest='url', default='http://localhost:8913')
    (options, args) = parser.parse_args()

    try:
        client = Client(options.url, "123456")
        temp_directory = tempfile.mkdtemp()

        remote_job_config = client.setup()
        output_directory = remote_job_config['outputs_directory']
        sep = remote_job_config['path_separator']
        
        temp_input_path = os.path.join(temp_directory, "input.txt")
        temp_config_path = os.path.join(temp_directory, "config.txt")
        temp_tool_path = os.path.join(temp_directory, "script.py")

        temp_input_file = open(temp_input_path, "w")
        temp_config_file = open(temp_config_path, "w")
        temp_tool_file = open(temp_tool_path, "w")
        try:
            temp_input_file.write("Hello world input!!@!")
            temp_tool_file.write("""
output = open(r'%s%s%s', 'w')
input = open(r'%s', 'r')
try:
    contents = input.read(1024)
    output.write(contents)
finally:
    output.close()
    input.close()
""" % (output_directory, sep, "output.moo", "config.txt"))
        finally:
            temp_input_file.close()
            temp_tool_file.close()
            temp_config_file.close()
            
        uploaded_input = client.upload_input(temp_input_path)
        uploaded_tool_file = client.upload_tool_file(temp_tool_path)
        uploaded_config = client.upload_config_file(temp_config_path, "hello world output")

        command = "python %s" % (uploaded_tool_file["path"])
        client.launch(command)
        result = client.wait()
        print result
        output_path = os.path.join(temp_directory, "output.moo")
        client.download_output(output_path)
        output_file = open(output_path, 'r')
        try:
            assert output_file.read() == "hello world output"
        finally:
            output_file.close()
    except BaseException, e:
        print "Exception: %s\n" % str(e)
        traceback.print_exc(e)
    finally:
        shutil.rmtree(temp_directory)
        client.clean()

if __name__ == "__main__":
    main()
