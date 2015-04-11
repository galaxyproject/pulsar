
``pulsar-check``
======================================

**Usage**::

    Script used to run an example job against a running Pulsar server.

**Help**

Exercises various features both the Pulsar client and server.


**Options**::


      -h, --help            show this help message and exit
      --url=URL             URL of the Pulsar web server to target.
      --private_token=PRIVATE_TOKEN
                            Private token used to authorize client, if the Pulsar
                            server specified a private_token in app.yml this must
                            match that value.
      --transport=TRANSPORT
                            Specify as 'curl' to use pycurl client for staging.
      --cache               Specify to test Pulsar caching during staging.
      --test_errors         Specify to exercise exception handling during staging.
      --suppress_output     
      --disable_cleanup     Specify to disable cleanup after the job, this is
                            useful to checking the files generated during the job
                            and stored on the Pulsar server.
    
