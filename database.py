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


class FeatureEntry:
    def __init__(self):
        self.examples = dict()

    def set_entry(self, name, headers):
        self.examples[name] = list(headers)


class FeatureDatabase:
    def __init__(self):
        self.libraries = dict()

    def add_entry(self, name, version, example, headers):
        if name not in self.libraries:
            self.libraries[name] = dict()

        lib = self.libraries[name]
        if version not in lib:
            lib[version] = FeatureEntry()

        fe = lib[version]
        fe.set_entry(example, headers)

    def search_all_for_headers(self, headers):
        res = []
        for (name, variants) in self.libraries.items():
            for (version, fe) in variants.items():
                for (example_name, example_headers) in fe.examples.items():
                    if len(example_headers) != 0 and set(example_headers).issubset(set(headers)):
                        res.append((name, version, example_name))
        return res

    def serialize(self):
        res = dict()
        for (name, variants) in self.libraries.items():
            if name not in res:
                res[name] = dict()
            for (version, fe) in variants.items():
                if version not in res[name]:
                    res[name][version] = dict()
                for (example_name, example_headers) in fe.examples.items():
                    if 'examples' not in res[name][version]:
                        res[name][version]['examples'] = dict()
                    res[name][version]['examples'][example_name] = list(example_headers)
        return res

    def deserialize(self, serialized):
        for (name, variants) in serialized.items():
            for version in variants.keys():
                for (example_name, example_headers) in variants[version]['examples'].items():
                    self.add_entry(name, version, example_name, list(example_headers))


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
    FEATURE_DATABASE_FILENAME = 'features.toml'

    def __init__(self, directory):
        self.root_path = Path(directory).expanduser()
        self.library_index = None
        self.header_dict = {}
        self.feature_data = FeatureDatabase()

    def load(self):
        self.library_index = self.read_library_index()
        if Path(self.root_path, self.HEADER_DICTIONARY_FILENAME).exists():
            self.read_header_dictionary()
        if Path(self.root_path, self.FEATURE_DATABASE_FILENAME).exists():
            self.read_feature_database()

    def save(self):
        if not self.library_index:
            raise ValueError('No library index data to save.')
        self.write_library_index(self.library_index)
        self.write_header_dictionary()
        self.write_feature_database()

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
        bar.finish()

    def search(self, header_name):
        res = []
        if header_name not in self.header_dict:
            return res
        libs = self.header_dict[header_name]
        for lib in libs:
            values = lib.split('\n')
            name = values[0]
            version = values[1]
            res.append({'name': name, 'version': version})
        return res

    def search_example_sketches(self, headers):
        return self.feature_data.search_all_for_headers(headers)

    def get_library_info_list(self):
        info_list = []
        for lib in self.library_index.libs:
            name = lib['name']
            version = lib['version']
            path = Path(self.root_path, self.LIBRARY_STORAGE_DIRECTORY, name, version)
            # Append the library data if the archive exists locally
            if self.is_downloaded(path):
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

    def add_feature_database_entry(self, lib_info, example_name, headers):
        self.feature_data.add_entry(lib_info.name, lib_info.version, example_name, headers)

    def is_downloaded(self, library_path):
        meta_path = Path(library_path, self.LIBRARY_METADATA_FILENAME)
        if meta_path.exists():
            with open(meta_path) as f:
                toml_string = f.read()
                metadata = toml.loads(toml_string)
                return metadata['could_download']
        else:
            return False

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
        for (k, v) in dict_from_toml.items():
            libs = set()
            for lib in v:
                lib_str = '{}\n{}'.format(lib['name'], lib['version'])
                libs.add(lib_str)
            res[k] = copy.deepcopy(libs)

        return res

    def secure_root_directory(self):
        if not self.root_path.exists():
            logging.debug('The root directory for the database does not exist. Creating one...')
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

    def write_feature_database(self):
        self.secure_root_directory()
        data_dict = self.feature_data.serialize()
        toml_string = toml.dumps(data_dict)
        with open(Path(self.root_path, self.FEATURE_DATABASE_FILENAME), 'w') as f:
            f.write(toml_string)

    def read_feature_database(self):
        with open(Path(self.root_path, self.FEATURE_DATABASE_FILENAME)) as f:
            toml_string = f.read()
            data_dict = toml.loads(toml_string)
            self.feature_data.deserialize(data_dict)

    def download_library(self, name, version, url, overwrite=False):
        # Create needed directories if they are not present
        lib_storage_path = Path(self.root_path, self.LIBRARY_STORAGE_DIRECTORY)
        if not lib_storage_path.exists():
            logging.debug('The library storage directory is not present. Creating one...')
            lib_storage_path.mkdir(0o755)
        target_library_path = Path(lib_storage_path, name)
        if not target_library_path.exists():
            logging.debug('The directory for the library is not present. Creating one...')
            target_library_path.mkdir(0o755)
        target_version_path = Path(target_library_path, version)
        if not target_version_path.exists():
            logging.debug('The directory for the version of the library is not present. Creating one...')
            target_version_path.mkdir(0o755)

        archives = list(target_version_path.glob('*.zip'))
        if not overwrite and len(archives) > 0:
            logging.debug('Some archives already exist. Skipping download.')
            return

        # Replace the content with the new archives
        for ar in archives:
            ar.unlink()
        archive_filename = urlparse(url).path.split('/')[-1]
        r = requests.get(url)
        dt = datetime.datetime.now(datetime.timezone.utc)
        if r.status_code != 200:
            logging.error('Unexpected HTTP status code: {}'.format(r.status_code))
            self.write_library_metadata(target_version_path, dt, False)
            logging.error('Could not download a library at: {}'.format(url))
        else:
            with open(Path(target_version_path, archive_filename), 'wb') as f:
                f.write(r.content)
                self.write_library_metadata(target_version_path, dt, True)

    def write_library_metadata(self, library_path, access_date, could_download):
        metadata_dict = {'access_date': access_date, 'could_download': could_download}
        toml_string = toml.dumps(metadata_dict)
        with open(Path(library_path, self.LIBRARY_METADATA_FILENAME), 'w') as f:
            f.write(toml_string)
