import shutil

from galaxy.util.resources import resource_path


def main():
    config_path = resource_path('pulsar.scripts', 'cvmfs_data/default.local')
    key_path = resource_path('pulsar.scripts', 'cvmfs_data/data.galaxyproject.org.pub')
    domain_path = resource_path('pulsar.scripts', 'cvmfs_data/galaxyproject.org.conf')

    # copy2?
    shutil.copy(config_path, "/etc/cvmfs/")
    shutil.copy(key_path, "/etc/cvmfs/keys/")
    shutil.copy(domain_path, "/etc/cvmfs/domain.d/")
