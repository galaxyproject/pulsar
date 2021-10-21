from os import makedirs
from os.path import join, dirname, exists
from string import Template
from galaxy.util.bunch import Bunch
from galaxy.objectstore import build_object_store_from_config

from .test_utils import TempDirectoryTestCase
from .test_utils import skip


class MockDataset:

    def __init__(self, id):
        self.id = id
        self.object_store_id = None


class PulsarObjectStoreTest(TempDirectoryTestCase):

    def __write(self, contents, name):
        path = join(self.temp_directory, name)
        directory = dirname(path)
        if not exists(directory):
            makedirs(directory)
        open(path, "wb").write(contents)
        return path

    @skip("No longer testing defunct objectstore")
    def test_pulsar_objectstore(self):
        # Define real object store used by Pulsar server.
        object_store_config_file = join(self.temp_directory, "object_store_conf.xml")
        with open(object_store_config_file, "w") as configf:
            config_template = Template("""<?xml version="1.0"?>
<object_store type="disk">
    <files_dir path="${temp_directory}"/>
    <extra_dir type="temp" path="${temp_directory}"/>
    <extra_dir type="job_work" path="${temp_directory}"/>
</object_store>
""")
            config_contents = config_template.safe_substitute(temp_directory=self.temp_directory)
            configf.write(config_contents)

        app_conf = dict(
            object_store_config_file=object_store_config_file,
            private_token="12345",
        )
        from .test_utils import test_pulsar_server
        with test_pulsar_server(app_conf=app_conf) as server:
            url = server.application_url
            # Define a proxy Pulsar object store.
            proxy_object_store_config_file = join(self.temp_directory, "proxy_object_store_conf.xml")
            with open(proxy_object_store_config_file, "w") as configf:
                config_template = Template("""<?xml version="1.0"?>
<object_store type="pulsar" url="$url" private_token="12345" transport="urllib">
  <!-- private_token is optional - see Pulsar documentation for more information. -->
  <!-- transport is optional, set to curl to use libcurl instead of urllib for communication with Pulsar. -->
</object_store>
""")
                contents = config_template.safe_substitute(url=url)
                configf.write(contents)

            config = Bunch(object_store_config_file=proxy_object_store_config_file)
            object_store = build_object_store_from_config(config=config)

            # Test no dataset with id 1 exists.
            absent_dataset = MockDataset(1)
            assert not object_store.exists(absent_dataset)

            # Write empty dataset 2 in second backend, ensure it is empty and
            # exists.
            empty_dataset = MockDataset(2)
            self.__write(b"", "000/dataset_2.dat")
            assert object_store.exists(empty_dataset)
            assert object_store.empty(empty_dataset)

            # Write non-empty dataset in backend 1, test it is not emtpy & exists.
            hello_world_dataset = MockDataset(3)
            self.__write(b"Hello World!", "000/dataset_3.dat")
            assert object_store.exists(hello_world_dataset)
            assert not object_store.empty(hello_world_dataset)

            # Test get_data
            data = object_store.get_data(hello_world_dataset)
            assert data == "Hello World!"

            data = object_store.get_data(hello_world_dataset, start=1, count=6)
            assert data == "ello W"

            # Test Size

            # Test absent and empty datasets yield size of 0.
            assert object_store.size(absent_dataset) == 0
            assert object_store.size(empty_dataset) == 0
            # Elsewise
            assert object_store.size(hello_world_dataset) > 0  # Should this always be the number of bytes?

            # Test percent used (to some degree)
            percent_store_used = object_store.get_store_usage_percent()
            assert percent_store_used > 0.0
            assert percent_store_used < 100.0

            # Test update_from_file test
            output_dataset = MockDataset(4)
            output_real_path = join(self.temp_directory, "000", "dataset_4.dat")
            assert not exists(output_real_path)
            output_working_path = self.__write(b"NEW CONTENTS", "job_working_directory1/example_output")
            object_store.update_from_file(output_dataset, file_name=output_working_path, create=True)
            assert exists(output_real_path)

            # Test delete
            to_delete_dataset = MockDataset(5)
            to_delete_real_path = self.__write(b"content to be deleted!", "000/dataset_5.dat")
            assert object_store.exists(to_delete_dataset)
            assert object_store.delete(to_delete_dataset)
            assert not object_store.exists(to_delete_dataset)
            assert not exists(to_delete_real_path)

            # Test json content.
            complex_contents_dataset = MockDataset(6)
            complex_content = b'{"a":6}'
            self.__write(complex_content, "000/dataset_6.dat")
            assert object_store.exists(complex_contents_dataset)
            data = object_store.get_data(complex_contents_dataset) == complex_content
