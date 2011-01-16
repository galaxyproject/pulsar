import sys
import subprocess
import os
import shutil
import thread
import time
import platform

class Manager(object):
    """
    >>> import tempfile
    >>> staging_directory = tempfile.mkdtemp()
    >>> shutil.rmtree(staging_directory)
    >>> manager = Manager(staging_directory)
    >>> assert os.path.exists(staging_directory)
    >>> command = "python -c \\"import sys; sys.stdout.write('Hello World!'); sys.stderr.write('moo')\\""
    >>> job_id = "123"
    >>> manager.setup_job_directory(job_id)
    >>> manager.launch(job_id, command)
    >>> while not manager.check_complete(job_id): pass
    >>> manager.return_code(job_id)
    0
    >>> manager.stdout_contents(job_id)
    'Hello World!'
    >>> manager.stderr_contents(job_id)
    'moo'
    >>> manager.clean_job_directory(job_id)
    >>> os.listdir(staging_directory)
    []
    >>> job_id = "234"
    >>> manager.setup_job_directory(job_id)
    >>> command = "python -c \\"import time; time.sleep(10000)\\""
    >>> manager.launch(job_id, command)
    >>> import time
    >>> time.sleep(0.1)
    >>> manager.kill(job_id)
    >>> manager.kill(job_id) # Make sure kill doesn't choke if pid doesn't exist
    >>> while not manager.check_complete(job_id): pass
    >>> manager.clean_job_directory(job_id)
    """
    def __init__(self, staging_directory):
	self.setup_staging_directory(staging_directory)

    def setup_staging_directory(self, staging_directory):
        assert not staging_directory == None
        if not os.path.exists(staging_directory):
            os.makedirs(staging_directory)
        assert os.path.isdir(staging_directory)        
        self.staging_directory = staging_directory

    def __job_file(self, job_id, name):
        return os.path.join(self.job_directory(job_id), name)

    def __read_job_file(self, job_id, name):
        path = self.__job_file(job_id, name)
        job_file = open(path, 'r')
        try:
            return job_file.read()
        finally:
            job_file.close()

    def __write_job_file(self, job_id, name, contents):
        path = self.__job_file(job_id, name)
        job_file = open(path, 'w')
        try:
            job_file.write(contents)
        finally:
            job_file.close()

    def record_pid(self, job_id, pid):
        self.__write_job_file(job_id, 'pid', str(pid))

    def get_pid(self, job_id):
        pid = None
        try:
            pid = self.__read_job_file(job_id, 'pid')
            if pid != None:
                pid = int(pid)
        except Exception, e:
            pass
        return pid

    def setup_job_directory(self, job_id):
        job_directory = self.job_directory(job_id)
        os.mkdir(job_directory)
        os.mkdir(self.inputs_directory(job_id))
        os.mkdir(self.outputs_directory(job_id))
        os.mkdir(self.working_directory(job_id))

    def clean_job_directory(self, job_id):
        job_directory = self.job_directory(job_id)
        if os.path.exists(job_directory):
            try:
                shutil.rmtree(job_directory)
            except:
                pass
        
    def job_directory(self, job_id):
        return os.path.join(self.staging_directory, job_id)

    def working_directory(self, job_id):
        return os.path.join(self.job_directory(job_id), 'working')

    def inputs_directory(self, job_id):
        return os.path.join(self.job_directory(job_id), 'inputs')

    def outputs_directory(self, job_id):
        return os.path.join(self.job_directory(job_id), 'outputs')

    def check_complete(self, job_id):
        return not os.path.exists(self.__job_file(job_id, 'pid'))

        #pid = self.get_pid(job_id)
        #if pid != None:
        #    try:
        #        os.waitpid(pid)
        #    except Exception, e:
        #        pass
        #while os.path.exists(self.__job_file(job_id, 'pid')):
        #    time.sleep(1)

    def return_code(self, job_id):
        return int(self.__read_job_file(job_id, 'return_code'))
    
    def stdout_contents(self, job_id):
        return self.__read_job_file(job_id, 'stdout')

    def stderr_contents(self, job_id):
        return self.__read_job_file(job_id, 'stderr')

    def __check_pid(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except OSError, e:
            return False

    def is_windows(self):
        return platform.system() == 'Windows'

    def kill(self, job_id):
        pid = self.get_pid(job_id)
        if pid == None:
            return
        if self.is_windows():
            try:
                subprocess.Popen("taskkill /F /T /PID %i" % pid , shell=True)
            except Exception, e:
                pass
        else:
            if self.__check_pid(pid):
                for sig in [ 15, 9 ]:
                    try:
                        os.killpg( pid, sig )
                    except OSError, e:
                        return
                    time.sleep(1)
                    if not self.__check_pid( pid ):
                        return 

    def monitor(self, job_id, proc, stdout, stderr):
        try:
            #stdout_contents = proc.stdout.read( 32768 )
            #stderr_contents = proc.stderr.read( 32768 )
            proc.wait()
            stdout.close()
            stderr.close()
            return_code = proc.returncode
            self.__write_job_file(job_id, 'return_code', str(return_code))
            #self.__write_job_file(job_id, 'stdout', stdout_contents)
            #self.__write_job_file(job_id, 'stderr', stderr_contents)
        finally:
            os.remove(self.__job_file(job_id, 'pid'))

    def launch(self, job_id, command_line):
        working_directory = self.working_directory(job_id)
        preexec_fn = None
        if not self.is_windows():
            preexec_fn = os.setpgrp
        stdout = open(self.__job_file(job_id, 'stdout'), 'w')
        stderr = open(self.__job_file(job_id, 'stderr'), 'w')
        proc = subprocess.Popen(args = command_line,
                                shell = True,
                                cwd = working_directory,
                                stdout = stdout,
                                stderr = stderr,
                                preexec_fn = preexec_fn)
        self.record_pid(job_id, proc.pid)
        thread.start_new_thread(self.monitor, (job_id, proc, stdout, stderr))
