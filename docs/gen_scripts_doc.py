#!/usr/bin/env python

import os
import subprocess
from string import Template


COMMAND_TEMPLATE = Template('''
${header}
======================================

${command_help}
''')

COMMANDS_TEMPLATE = """
Scripts
-----------------

This section describes some of the various scripts that are distributed with
Pulsar.

.. include:: scripts/pulsar.rst
"""

scripts = {
    "pulsar_config_windows": "pulsar-config (Windows)",
    "pulsar_config": "pulsar-config (\\*nix)",
    "pulsar_check": "pulsar-check",
    "pulsar_main": "pulsar-main"
}

command_doc_dir = os.path.join("docs", "scripts")
commands = COMMANDS_TEMPLATE

for (section, script_description) in scripts.items():
    command = script_description.split(" ")[0]
    if "Windows" in script_description:
        os.environ["MOCK_WINDOWS"] = "1"
    elif "MOCK_WINDOWS" in os.environ:
        del os.environ["MOCK_WINDOWS"]

    output = subprocess.check_output([command, "--help"])

    # def clean_rst_line(line):
    #     if line.startswith("    "):
    #         return line[4:]
    #     else:
    #         return line

    lines = output.split("\n")
    new_lines = []
    help_lines = False
    option_lines = False
    for line in lines:
        if line.lower().startswith("usage: "):
            new_lines.append("**Usage**::\n\n    %s" % line[len("usage: "):])
            usage_lines = True
        elif usage_lines and line.startswith(" "):
            new_lines.append("    %s" % line[len("usage: "):])
        elif usage_lines:
            usage_lines = False
            new_lines.append("\n**Help**\n")
            help_lines = True
        elif line.startswith("Options:"):
            # optparse-style
            help_lines = False
            new_lines.append("**Options**::\n\n")
            option_lines = True
        elif line.startswith("optional arguments:"):
            # argparse-style
            help_lines = False
            new_lines.append("**Options**::\n\n")
            option_lines = True
        elif option_lines:
            new_lines.append("    %s" % line)
        elif help_lines:
            new_lines.append(line)
    header = script_description.split(" ")
    header[0] = "``%s``" % header[0]
    text = COMMAND_TEMPLATE.safe_substitute(
        header=" ".join(header),
        command_help="\n".join(new_lines),
    )
    commands += "\n.. include:: scripts/%s.rst" % section
    open(os.path.join(command_doc_dir, section + ".rst"), "w").write(text)

open(os.path.join("docs", "scripts.rst"), "w").write(commands)
