import datetime


class LibraryIndex:
    def __init__(self, libs):
        self.libs = libs
        self.access_date = datetime.datetime.now(datetime.timezone.utc)

    def set_access_date(self, dt):
        self.access_date = dt


def from_json_dict(d):
    if 'libraries' not in d:
        raise ValueError('library key is not present.')

    libs = d['libraries']
    if not isinstance(libs, list):
        raise ValueError('library does not contain a valid list.')

    return LibraryIndex(libs)


def from_database_toml_dict(d):
    if 'libs' not in d:
        raise ValueError('libs key is not present.')
    if 'access_date' not in d:
        raise ValueError('access_date key is not present.')

    res = LibraryIndex(d['libs'])
    res.set_access_date(d['access_date'])
    return res
