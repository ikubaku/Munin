import os
from pathlib import Path
import logging
from urllib.parse import urlparse
import datetime
import copy
import toml
import requests
from progress.bar import Bar
import library_index


class LibraryInfo:
    def __init__(self, name, version, path):
        self.name = name
        self.version = version
        self.path = path


class Database:
    LIBRARY_INDEX_FILENAME = 'library_index.toml'
    LIBRARY_STORAGE_DIRECTORY = 'libraries'
    LIBRARY_METADATA_FILENAME = 'meta.toml'
    HEADER_DICTIONARY_FILENAME = 'headers.toml'

    def __init__(self, directory):
        self.root_path = Path(directory).expanduser()
        self.library_index = None
        self.header_dict = {}

    def load(self):
        self.library_index = self.read_library_index()
        if Path(self.root_path, self.HEADER_DICTIONARY_FILENAME).exists():
            self.read_header_dictionary()

    def save(self):
        if not self.library_index:
            raise ValueError('No library index data to save.')
        self.write_library_index(self.library_index)
        self.write_header_dictionary()

    def download(self, overwrite=False):
        if not self.library_index:
            raise ValueError('No library index. Cannot download packages.')

        self.secure_root_directory()
        n_libs = len(self.library_index.libs)
        print('Downloading {} library archives...'.format(n_libs))
        bar = Bar('PROGRESS', max=n_libs)
        for lib in self.library_index.libs:
            name = lib['name']
            version = lib['version']
            url = lib['url']
            self.download_library(name, version, url, overwrite)
            bar.next()

    def get_library_info_list(self):
        info_list = []
        for lib in self.library_index.libs:
            name = lib['name']
            version = lib['version']
            path = Path(self.root_path, self.LIBRARY_STORAGE_DIRECTORY, name, version)
            info_list.append(LibraryInfo(name, version, path))
        return info_list

    # For the entries of the set of libraries, we use the name and the version as strings concatenated by '\n'.
    # This makes the library information serializable, which is not the case if we use the dictionary.
    def add_header_dictionary_entry(self, lib_info, headers):
        for h in headers:
            h = str(h)
            if h in self.header_dict:
                # Add a library candidate if not yet added
                self.header_dict[h].add('{}\n{}'.format(lib_info.name, lib_info.version))
            else:
                # Create a new set of candidates for the header file
                self.header_dict[h] = {'{}\n{}'.format(lib_info.name, lib_info.version)}

    def serialize_header_dictionary(self):
        res = {}
        for (k, v) in self.header_dict.items():
            libs = []
            for lib in v:
                values = lib.split('\n')
                name = values[0]
                version = values[1]
                libs.append({'name': name, 'version': version})
            res[k] = copy.deepcopy(libs)

        return res

    def deserialize_header_dictionary(self, dict_from_toml):
        res = {}
        for (k, v) in dict_from_toml:
            libs = set()
            for lib in v:
                lib_str = '{}\n{}'.format(lib['name'], lib['version'])
                libs.add(lib_str)
            res[k] = copy.deepcopy(libs)

        return res

    def secure_root_directory(self):
        if not self.root_path.exists():
            logging.info('The root directory for the database does not exist. Creating one...')
            self.root_path.mkdir(0o755)

    def write_library_index(self, index):
        self.secure_root_directory()
        with open(os.path.join(self.root_path, self.LIBRARY_INDEX_FILENAME), 'w') as f:
            toml_string = toml.dumps(index.__dict__)
            f.write(toml_string)

    def read_library_index(self):
        with open(os.path.join(self.root_path, self.LIBRARY_INDEX_FILENAME)) as f:
            toml_string = f.read()
            index_dict = toml.loads(toml_string)
            return library_index.from_database_toml_dict(index_dict)

    def write_header_dictionary(self):
        self.secure_root_directory()
        data_dict = self.serialize_header_dictionary()
        toml_string = toml.dumps(data_dict)
        with open(Path(self.root_path, self.HEADER_DICTIONARY_FILENAME), 'w') as f:
            f.write(toml_string)

    def read_header_dictionary(self):
        with open(Path(self.root_path, self.HEADER_DICTIONARY_FILENAME)) as f:
            toml_string = f.read()
            data_dict = toml.loads(toml_string)
            self.header_dict = self.deserialize_header_dictionary(data_dict)

    def download_library(self, name, version, url, overwrite=False):
        # Create needed directories if they are not present
        lib_storage_path = Path(self.root_path, self.LIBRARY_STORAGE_DIRECTORY)
        if not lib_storage_path.exists():
            logging.info('The library storage directory is not present. Creating one...')
            lib_storage_path.mkdir(0o755)
        target_library_path = Path(lib_storage_path, name)
        if not target_library_path.exists():
            logging.info('The directory for the library is not present. Creating one...')
            target_library_path.mkdir(0o755)
        target_version_path = Path(target_library_path, version)
        if not target_version_path.exists():
            logging.info('The directory for the version of the library is not present. Creating one...')
            target_version_path.mkdir(0o755)

        archives = list(target_version_path.glob('*.zip'))
        if not overwrite and len(archives) > 0:
            logging.info('Some archives already exist. Skipping download.')
            return

        # Replace the content with the new archives
        for ar in archives:
            ar.unlink()
        archive_filename = urlparse(url).path.split('/')[-1]
        r = requests.get(url)
        dt = datetime.datetime.now(datetime.timezone.utc)
        if r.status_code != 200:
            logging.warning('Unexpected HTTP status code: {}'.format(r.status_code))
            self.write_library_metadata(target_version_path, dt, False)
            logging.warning('Continuing downloading other libraries')
        else:
            with open(Path(target_version_path, archive_filename), 'wb') as f:
                f.write(r.content)
                self.write_library_metadata(target_version_path, dt, True)

    def write_library_metadata(self, library_path, access_date, could_download):
        metadata_dict = {'access_date': access_date, 'could_download': could_download}
        toml_string = toml.dumps(metadata_dict)
        with open(Path(library_path, self.LIBRARY_METADATA_FILENAME), 'w') as f:
            f.write(toml_string)
