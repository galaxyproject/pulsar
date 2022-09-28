import shutil

import pkg_resources


def main():
    config_path = pkg_resources.resource_filename('pulsar.scripts', 'cvmfs_data/default.local')
    key_path = pkg_resources.resource_filename('pulsar.scripts', 'cvmfs_data/data.galaxyproject.org.pub')
    domain_path = pkg_resources.resource_filename('pulsar.scripts', 'cvmfs_data/galaxyproject.org.conf')

    # copy2?
    shutil.copy(config_path, "/etc/cvmfs/")
    shutil.copy(key_path, "/etc/cvmfs/keys/")
    shutil.copy(domain_path, "/etc/cvmfs/domain.d/")
