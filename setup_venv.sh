#!/bin/bash

project_directory="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $project_directory
if [ ! -e .venv ]
then
    # If virtualenv is not already installed, install it locally
    command -v virtualenv >/dev/null 2>&1 || { . tools/install_virtualenv.sh; }
    
    # Install venv
    python tools/install_venv.py
fi

