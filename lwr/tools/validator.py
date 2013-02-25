from xml.etree.ElementTree import fromstring
from re import escape, compile

from os.path import join
from lwr.util import is_in_directory


class ExpressionValidator(object):

    def __init__(self, xml_el):
        if type(xml_el) == str:
            xml_el = fromstring(xml_el)
        self.xml_el = xml_el

    def validate(self, job_directory, string):
        regex = "^%s$" % self._expression_to_regex(job_directory, self.xml_el)
        match = compile(regex).match(string)
        validated = match is not None
        if validated:
            for group in match.groups():
                if not is_in_directory(group, join(job_directory.path, "inputs")):
                    validated = False
                    break
        return validated

    def _expression_to_regex(self, job_directory, element):
        return r"\s+".join([self._element_to_regex(child, job_directory) for child in list(element)])

    def _element_to_regex(self, element, job_directory):
        tag = element.tag
        method_name = "_%s_to_regex" % tag
        try:
            method = getattr(self, method_name)
        except NameError:
            raise NameError("Unknown XML validation tag [%s]" % tag)
        return method(element, job_directory)

    def _literal_to_regex(self, element, job_directory):
        return escape(self.__value_or_text(element))

    def _parameter_to_regex(self, element, job_directory):
        parameter_name = element.get('name')
        value_regex = self._expression_to_regex(job_directory, element)
        return r"%s(?:=|\s+)%s" % (parameter_name, value_regex)

    def _integer_to_regex(self, element, job_directory):
        return r"\d+"

    def _float_to_regex(self, element, job_directory):
        # http://stackoverflow.com/a/9392612
        return r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"

    def _tool_wrapper_to_regex(self, element, job_directory):
        wrapper_name = self.__value_or_text(element, "name")
        path = join(job_directory.path, "tool_files", wrapper_name)
        return escape(path)

    def _configfile_to_regex(self, element, job_directory):
        wrapper_name = self.__value_or_text(element, "name")
        path = join(job_directory.path, "configs", wrapper_name)
        return escape(path)

    def _input_to_regex(self, element, job_directory):
        return r"(%s.*)" % escape(join(job_directory.path, "inputs"))

    def __value_or_text(self, element, attribute="value"):
        value = element.get(attribute, None)
        if value is None:
            value = element.text
        return value
