import toml


class MuninConfig:
    def __init__(self, library_index_url, database_root):
        self.library_index_url = library_index_url
        self.database_root = database_root


def read_config(filename):
    with open(filename) as f:
        config_dict = toml.loads(f.read())
        return MuninConfig(
            config_dict['library_index_url'],
            config_dict['database_root']
        )
