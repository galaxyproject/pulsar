from test_utils import TempDirectoryTestCase

from lwr.util import JobDirectory
from lwr.tools.validator import ExpressionValidator

from os.path import join


class ValidatorTest(TempDirectoryTestCase):

    def test_literal(self):
        xml = """
        <expression>
            <literal value="tophat2" />
        </expression>"""
        self.__assertValid(xml, "tophat2")
        self.__assertInvalid(xml, "bowtie")

    def test_two_literals(self):
        xml = """
        <expression>
            <literal value="python" />
            <literal value="setup.py" />
        </expression>"""
        self.__assertValid(xml, "python setup.py")
        self.__assertInvalid(xml, "pythonsetup.py")

    def test_parameter(self):
        xml = """
        <expression>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev">
                <literal value="4" />
            </parameter>
        </expression>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev 4")
        self.__assertValid(xml, "tophat2 --mate-std-dev=4")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=5")

    def test_integer(self):
        xml = """
        <expression>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev">
                <integer />
            </parameter>
        </expression>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev 4")
        self.__assertValid(xml, "tophat2 --mate-std-dev=4")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=5.0")

    def test_float(self):
        xml = """
        <expression>
            <literal value="tophat2" />
            <parameter name="--mate-std-dev">
                <float />
            </parameter>
        </expression>"""
        self.__assertValid(xml, "tophat2 --mate-std-dev 4")
        self.__assertValid(xml, "tophat2 --mate-std-dev=4")
        self.__assertValid(xml, "tophat2 --mate-std-dev=5.0")
        self.__assertValid(xml, "tophat2 --mate-std-dev=4e10")
        self.__assertValid(xml, "tophat2 --mate-std-dev=-1.0e10")
        self.__assertValid(xml, "tophat2 --mate-std-dev=-.0e10")
        self.__assertInvalid(xml, "tophat2 --mate-std-dev=cat")

    def test_tool_wrapper(self):
        xml = """
        <expression>
            <tool_wrapper name="tool1_wrapper.py" />
        </expression>
        """
        self.__assertValid(xml, "%s" % self.__job_file('tool_files', 'tool1_wrapper.py'))
        self.__assertInvalid(xml, "tool1_wrapper.py")

    def test_config_file(self):
        xml = """
        <expression>
            <literal value="tophat2" />
            <configfile name="top_opts" />
        </expression>
        """
        self.__assertValid(xml, "tophat2 %s" % self.__job_file('configs', 'top_opts'))
        self.__assertInvalid(xml, "tophat2 ../%s" % self.__job_file('configs', 'top_opts'))
        self.__assertInvalid(xml, "tophat2 %s" % self.__job_file('configs', 'top_optsX'))

    def test_input_file(self):
        xml = """
        <expression>
            <literal value="tophat2" />
            <input />
        </expression>
        """
        self.__assertValid(xml, "tophat2 %s" % self.__job_file("inputs", "dataset_23412.dat"))
        self.__assertInvalid(xml, "tophat2 %s/../../../dataset23412.dat" % self.__job_file("inputs", "dataset_23412.dat"))
        self.__assertInvalid(xml, "tophat2 ../%s" % self.__job_file("inputs", "dataset_23412.dat"))

    def test_two_inputs(self):
        xml = """
        <expression>
            <literal value="tophat2" />
            <input />
            <input />
        </expression>
        """
        self.__assertValid(xml, "tophat2 %s %s" % (self.__job_file("inputs", "dataset_23412.dat"),
                                                   self.__job_file("inputs", "dataset_1.dat")))

        self.__assertInvalid(xml, "tophat2 %s ../%s" % (self.__job_file("inputs", "dataset_23412.dat"),
                                                        self.__job_file("inputs", "dataset_1.dat")))

    def test_outputs_file(self):
        xml = """
        <expression>
            <literal value="tophat2" />
            <output />
            <output />
        </expression>
        """
        self.__assertValid(xml, "tophat2 %s %s" % (self.__job_file("outputs", "dataset_23412.dat"),
                                                   self.__job_file("outputs", "dataset_1.dat")))

        self.__assertInvalid(xml, "tophat2 %s ../%s" % (self.__job_file("outputs", "dataset_23412.dat"),
                                                        self.__job_file("outputs", "dataset_1.dat")))

    def test_outputs_from_work_dir(self):
        xml = """
        <expression>
            <literal value="tophat2" />
            <output />
            <output from_work_dir="junctions.bed" />
        </expression>
        """
        self.__assertValid(xml, "tophat2 %s %s" % (self.__job_file("outputs", "dataset_23412.dat"),
                                                   self.__job_file("working", "junctions.bed")))

        self.__assertInvalid(xml, "tophat2 %s ../%s" % (self.__job_file("outputs", "dataset_23412.dat"),
                                                        self.__job_file("working", "..", "junctions.bed")))

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
        self.assertTrue(self.__is_valid(xml, contents), "%s did not validate against %s" % (contents, xml))

    def __assertInvalid(self, xml, contents):
        self.assertFalse(self.__is_valid(xml, contents), "%s falsely validated against %s" % (contents, xml))
