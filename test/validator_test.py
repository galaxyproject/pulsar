from os.path import join

from pulsar.managers.base import JobDirectory
from pulsar.tools.validator import ExpressionValidator
from .test_utils import TempDirectoryTestCase


class ValidatorTest(TempDirectoryTestCase):

    def test_literal(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
        </command_validator>"""
        self.__assertValid(xml, "tophat2")
        self.__assertInvalid(xml, "bowtie")

    def test_two_literals(self):
        xml = """
        <command_validator>
            <literal value="python" />
            <literal value="setup.py" />
        </command_validator>"""
        self.__assertValid(xml, "python setup.py")
        self.__assertInvalid(xml, "pythonsetup.py")

    def test_parameter(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev">
                <literal value="4" />
            </parameter>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev 4")
        self.__assertValid(xml, "tophat2 --mate-std-dev=4")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=5")

    def test_integer(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev">
                <integer />
            </parameter>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev 4")
        self.__assertValid(xml, "tophat2 --mate-std-dev=4")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=5.0")

    def test_float(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev">
                <float />
            </parameter>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev 4")
        self.__assertValid(xml, "tophat2 --mate-std-dev=4")
        self.__assertValid(xml, "tophat2 --mate-std-dev=5.0")
        self.__assertValid(xml, "tophat2 --mate-std-dev=4e10")
        self.__assertValid(xml, "tophat2 --mate-std-dev=-1.0e10")
        self.__assertValid(xml, "tophat2 --mate-std-dev=-.0e10")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=cat")

    def test_tool_wrapper(self):
        xml = """
        <command_validator>
            <tool_wrapper name="tool1_wrapper.py" />
        </command_validator>
        """
        self.__assertValid(xml, "%s" % self.__job_file('tool_files', 'tool1_wrapper.py'))
        self.__assertInvalid(xml, "tool1_wrapper.py")

    def test_config_file(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <configfile name="top_opts" />
        </command_validator>
        """
        self.__assertValid(xml, "tophat2 %s" % self.__job_file('configs', 'top_opts'))
        self.__assertInvalid(xml, "tophat2 ../%s" % self.__job_file('configs', 'top_opts'))
        self.__assertInvalid(xml, "tophat2 %s" % self.__job_file('configs', 'top_optsX'))

    def test_input_file(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <input />
        </command_validator>
        """
        self.__assertValid(xml, "tophat2 %s" % self.__job_file("inputs", "dataset_23412.dat"))
        self.__assertInvalid(xml, "tophat2 %s/../../../dataset23412.dat" % self.__job_file("inputs", "dataset_23412.dat"))
        self.__assertInvalid(xml, "tophat2 ../%s" % self.__job_file("inputs", "dataset_23412.dat"))

    def test_two_inputs(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <input />
            <input />
        </command_validator>
        """
        self.__assertValid(xml, "tophat2 {} {}".format(
            self.__job_file("inputs", "dataset_23412.dat"),
            self.__job_file("inputs", "dataset_1.dat")
        ))

        self.__assertInvalid(xml, "tophat2 {} ../{}".format(
            self.__job_file("inputs", "dataset_23412.dat"),
            self.__job_file("inputs", "dataset_1.dat")
        ))

    def test_outputs_file(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <output />
            <output />
        </command_validator>
        """
        self.__assertValid(xml, "tophat2 {} {}".format(
            self.__job_file("outputs", "dataset_23412.dat"),
            self.__job_file("outputs", "dataset_1.dat")
        ))

        self.__assertInvalid(xml, "tophat2 {} ../{}".format(
            self.__job_file("outputs", "dataset_23412.dat"),
            self.__job_file("outputs", "dataset_1.dat")
        ))

    def test_outputs_from_work_dir(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <output />
            <output from_work_dir="junctions.bed" />
        </command_validator>
        """
        self.__assertValid(xml, "tophat2 {} {}".format(
            self.__job_file("outputs", "dataset_23412.dat"),
            self.__job_file("working", "junctions.bed")
        ))

        self.__assertInvalid(xml, "tophat2 {} ../{}".format(
            self.__job_file("outputs", "dataset_23412.dat"),
            self.__job_file("working", "..", "junctions.bed")
        ))

    def test_single_quotes(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev">
                <literal value="4" single_quote="true" />
            </parameter>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev '4'")
        self.__assertValid(xml, "tophat2 --mate-std-dev='4'")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=4")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=\"4\"")

    def test_double_quotes(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev">
                <literal value="4" double_quote="true" />
            </parameter>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev \"4\"")
        self.__assertValid(xml, "tophat2 --mate-std-dev=\"4\"")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=4")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev='4'")

    def test_min(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev" min="0">
                <literal value="4" double_quote="true" />
            </parameter>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev \"4\"")
        self.__assertValid(xml, "tophat2 ")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=5")

    def test_max(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <regex value="[a-z]" max="2"/>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 a")
        self.__assertValid(xml, "tophat2 a b")
        self.__assertInvalid(xml, "tophat2 a b c")

    def test_group(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <group>
                <literal value="a" />
                <regex value="[b-z]+" />
                <literal value="a" />
            </group>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 aba")
        self.__assertValid(xml, "tophat2 abba")
        self.__assertInvalid(xml, "tophat2 abbbaa")
        self.__assertInvalid(xml, "tophat2 abb")

    def test_group_separate_by(self):
        xml = """
        <command_validator>
            <literal value="tophat2" />
            <group separate_by="x">
                <literal value="a" />
                <regex value="[b-z]+" />
                <literal value="a" />
            </group>
        </command_validator>"""
        self.__assertValid(xml, "tophat2 axbxa")
        self.__assertValid(xml, "tophat2 axbxbxa")
        self.__assertInvalid(xml, "tophat2 abba")
        self.__assertInvalid(xml, "tophat2 axbxbxbxaxa")

    def __job_file(self, *args):
        return join(self.temp_directory, '1', *args)

    def __validator(self, xml):
        return ExpressionValidator(xml)

    @property
    def job_directory(self):
        return JobDirectory(self.temp_directory, '1')

    def __is_valid(self, xml, contents):
        return self.__validator(xml).validate(self.job_directory, contents)

    def __assertValid(self, xml, contents):
        self.assertTrue(self.__is_valid(xml, contents), "{} did not validate against {}".format(contents, xml))

    def __assertInvalid(self, xml, contents):
        self.assertFalse(self.__is_valid(xml, contents), "{} falsely validated against {}".format(contents, xml))
