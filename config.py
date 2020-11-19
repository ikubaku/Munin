import toml


class MuninConfig:
    def __init__(self, library_index_url, database_root, temp_dir):
        self.library_index_url = library_index_url
        self.database_root = database_root
        self.temp_dir = temp_dir


def read_config(filename):
    with open(filename) as f:
        config_dict = toml.loads(f.read())
        return MuninConfig(
            config_dict['library_index_url'],
            config_dict['database_root'],
            config_dict['temp_dir']
        )
