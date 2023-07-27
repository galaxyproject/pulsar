from .test_utils import get_test_toolbox, temp_job_directory
from os.path import join
from os import makedirs


def test_load_simple_tool():
    toolbox = get_test_toolbox()
    tool1 = toolbox.get_tool("tool1")
    assert tool1.version == "0.1"


def test_command_validation():
    toolbox = get_test_toolbox()
    tool1 = toolbox.get_tool("tool1")
    with temp_job_directory() as job_directory:
        wrapper_path = join(job_directory.tool_files_directory(), "tool1_wrapper.py")
        config_path = join(job_directory.configs_directory(), "config1")
        valid_command = "python %s --config %s" % \
            (wrapper_path, config_path)
        assert tool1.inputs_validator.validate_command(job_directory, valid_command)


def test_config_validation():
    toolbox = get_test_toolbox()
    tool1 = toolbox.get_tool("tool1")
    with temp_job_directory() as job_directory:
        configs_dir = job_directory.configs_directory()
        config_path = join(configs_dir, "config1")
        makedirs(configs_dir)
        open(config_path, "w").write("\n   --option1='Hello' \n")
        assert tool1.inputs_validator.validate_config(job_directory, "config1", config_path)
