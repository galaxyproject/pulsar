from os.path import join
from re import compile, escape
from xml.etree.ElementTree import fromstring

from galaxy.util import in_directory


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
                if not in_directory(group, join(job_directory.path, "inputs")) and \
                   not in_directory(group, join(job_directory.path, "outputs")):
                    validated = False
                    break
        return validated

    def _expression_to_regex(self, job_directory, element, default_sep="*spaces*"):
        sep = element.get("separate_by", default_sep)
        if sep == "*spaces*":
            join_on = r" +"
        elif sep == "*whitespace*":
            join_on = r"\s+"
        else:
            join_on = escape(sep)
        return join_on.join([self._element_to_regex(child, job_directory, join_on) for child in list(element)])

    def _element_to_regex(self, element, job_directory, join_on):
        tag = element.tag
        method_name = "_%s_to_regex" % tag
        try:
            method = getattr(self, method_name)
        except NameError:
            raise NameError("Unknown XML validation tag [%s]" % tag)
        regex = method(element, job_directory)
        if self.__is_true(element.get("single_quote", "false")):
            regex = r"'%s'" % regex
        if self.__is_true(element.get("double_quote", "false")):
            regex = r'"%s"' % regex
        min_count = int(element.get("min", "1"))
        max_count = int(element.get("max", "1"))
        assert max_count > 0
        if min_count != 1 or max_count != 1:
            single_regex = r"(?:%s)" % regex
            first = "%s%s" % (single_regex, "?" if min_count == 0 else "")
            rest = r"(?:%s%s){%d,%d}" % (join_on, regex, max(min_count - 1, 0), max_count - 1)
            regex = "%s%s" % (first, rest)
        return regex

    def __is_true(self, str):
        return str and str.lower() == "true"

    def _literal_to_regex(self, element, job_directory):
        return escape(self.__value_or_text(element))

    def _regex_to_regex(self, element, job_directory):
        return self.__value_or_text(element)

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
        if not wrapper_name:
            raise Exception("Invalid validator - found tool_wrapper element without name.")
        path = join(job_directory.path, "tool_files", wrapper_name)
        return escape(path)

    def _configfile_to_regex(self, element, job_directory):
        wrapper_name = self.__value_or_text(element, "name")
        path = join(job_directory.path, "configs", wrapper_name)
        return escape(path)

    def _input_to_regex(self, element, job_directory):
        return r"(%s.*)" % escape(join(job_directory.path, "inputs"))

    def _output_to_regex(self, element, job_directory):
        work_dir_file = element.get("from_work_dir", None)
        regex = r"(%s.*)" % escape(join(job_directory.path, "outputs"))
        if work_dir_file:
            regex = r"%s" % escape(join(job_directory.path, "working", work_dir_file))
        return regex

    def _group_to_regex(self, element, job_directory):
        return self._expression_to_regex(job_directory, element, default_sep="")

    def __value_or_text(self, element, attribute="value"):
        value = element.get(attribute, None)
        if value is None:
            value = element.text
        return value
