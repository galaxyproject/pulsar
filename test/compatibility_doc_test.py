import importlib.util
import os

GEN_SCRIPT = os.path.join(os.path.dirname(__file__), os.pardir, "docs", "gen_compatibility_doc.py")


def _gen_module():
    spec = importlib.util.spec_from_file_location("gen_compatibility_doc", GEN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compatibility_rst_is_current_and_matrix_is_consistent():
    assert _gen_module().main(["--check"]) == 0
