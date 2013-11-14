-------------------------------
Configuring a Public LWR Server
-------------------------------

An LWR server can be pointed at a Galaxy toolbox XML file and opened
to the world. By default, an LWR is allowed to run anything Galaxy (or
other client) sends it. The toolbox and referenced tool files are used
to restrict what what the LWR will run.

This can be sort of thought of as web services defined by Galaxy tool
files - with all the advantages (dead simple configuration for
clients, ability to hide details related date and computation) and
disadvantages (lack of reproducibility if the LWR server goes away,
potential lack of transparency).

Securing a Public LWR
---------------------

The following options should be set in ``server.ini`` to configure a
public `LWR` server.

- ``assign_ids=uuid`` - By default the `LWR` will just the ids Galaxy
  instances. Setting this setting to ``uuid`` will result in each job
  being assigned a UUID, ensuring different clients will not and
  cannot interfer with each other.

- ``tool_config_files=/path/to/tools.xml`` - As noted above, this is used to
  restrict what tools clients can run. All tools on public LWR servers
  should have validators for commands (and optionally for configfiles)
  defined. The syntax for these elements can be found in the
  `ValidatorTest <https://bitbucket.org/jmchilton/lwr/src/tip/test/validator_test.py>`_ test case.

Writing Secure Tools
--------------------

Validating in this fashion is complicated and potentially error prone,
so it is advisable to keep command-lines as simple as
possible. configfiles and reorganizing parameter handling in wrappers
scripts can assist in this.

Consider the following simple example:

``tool.xml``::

    <tool>
       <command interpreter="python">wrapper.py --input1 'Text' --input2 'Text2' --input3 4.5</command>
       ...


``wrapper.py``::

    def main():
         parser = OptionParser()
         parser.add_option("--input1")
         parser.add_option("--input2")
         parser.add_option("--input3")
         (options, args) = parser.parse_args()

Even this simple example is easier to validate and secure if it is
reworked as so:

``tool.xml``::
    
    <tool>
      <configfiles>
        <configfile name="args">--input1 'Text' --input2 'Text2' --input3 4.5</configfile>
      </configfiles>
      <command interpreter="python">wrapper.py $args</command>
      ...

``wrapper.py``::

    import sys, shlex
    
    def main():
        args_config = sys.argv[1]
        args_string = open(args_config, "r").read()
      
        parser = OptionParser()
        parser.add_option("--input1")
        parser.add_option("--input2")
        parser.add_option("--input3")
        (options, args) = parser.parse_args(shlex.split(args_string))    
