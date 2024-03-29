import os
from pathlib import Path
import logging
from urllib.parse import urlparse
import datetime
import copy
import zipfile
from zipfile import ZipFile, BadZipFile
import re
import toml
import requests
from progress.bar import Bar
import semver
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

    # Version specifiers for the extraction methods
    ALL_VERSIONS = 0
    LATEST_VERSIONS = 1

    def __init__(self, directory):
        self.root_path = Path(directory).expanduser()
        self.library_index = None
        self.header_dict = {}
        self.feature_data = FeatureDatabase()

    def load(self, force=False):
        if self.library_index is None or force:
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

    def restore(self):
        if not self.library_index:
            raise ValueError('No library index. Cannot download packages.')

        n_libs = len(self.library_index.libs)
        print('Downloading {} library archives...'.format(n_libs))
        bar = Bar('PROGRESS', max=n_libs)
        for lib in self.library_index.libs:
            name = lib['name']
            version = lib['version']
            url = lib['url']
            self.restore_library(name, version, url)
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

    # Generate the list of sources to extract from the list of examples and the version restriction.
    # examples is a list of (library_name, version, example_name) tuples.
    # Returns the list of (LibraryInfo, example_name)
    # where example_name is the example sketch of the library for LibraryInfo.
    def compute_extract_targets(self, examples=None, version_flag=ALL_VERSIONS):
        # Collect required information into a sequence of (LibraryInfo, [example_name]).
        if examples is None:
            info_list = self.get_library_info_list()
            examples_list = None
        else:
            # TODO: self.search_example_sketches may return data in dictionary so that this process become not
            #  necessary.
            temp_dict = {}
            info_list = []
            examples_list = []
            for e in examples:
                # 'library_name\nversion'
                (library_name, version, example_name) = e
                temp_key = '\n'.join([library_name, version])
                if temp_key in temp_dict:
                    temp_dict[temp_key].append(example_name)
                else:
                    temp_dict[temp_key] = [example_name]
            for (k, v) in temp_dict.items():
                (library_name, version) = k.split('\n')
                example_names = v
                path = Path(self.root_path, self.LIBRARY_STORAGE_DIRECTORY, library_name, version)
                if self.is_downloaded(path):
                    info_list.append(LibraryInfo(library_name, version, path))
                    examples_list.append(example_names)

        # If the version_flag is set, remove unnecessary versions.
        max_version = {}
        variant_bucket = {}
        if version_flag != Database.ALL_VERSIONS:
            for i in range(len(info_list)):
                info = info_list[i]
                if examples_list is not None:
                    ex = examples_list[i]
                else:
                    ex = None

                if info.name in variant_bucket:
                    if version_flag == Database.LATEST_VERSIONS:
                        cmp_res = semver.compare(max_version[info.name], info.version) < 0
                    else:
                        raise ValueError('BUG: Invalid version flag.')
                    if cmp_res:
                        max_version[info.name] = info.version
                        variant_bucket[info.name] = [(info, ex)]
                else:
                    max_version[info.name] = info.version
                    variant_bucket[info.name] = [(info, ex)]
        extract_targets = []
        for v in variant_bucket.values():
            extract_targets.extend(v)
        return extract_targets

    # Returns the list of ([example_source_path,...], library_name, library_version, archive_path, archive_root)
    # or None on failure
    def get_example_sketches_to_extract(self, examples=None, version_flag=ALL_VERSIONS):
        res = []
        targets = self.compute_extract_targets(examples, version_flag)
        for ex in targets:
            name = ex[0].name
            version = ex[0].version
            library_storage_location = ex[0].path
            examples = ex[1]
            ar = list(library_storage_location.glob('*.zip'))[0]
            try:
                z = ZipFile(ar)
            except BadZipFile as ex:
                logging.error('Invalid Zip archive: {}'.format(ar))
                logging.error('Description: {}'.format(str(ex.args[0])))
                return
            with z:
                # Locate the root directory of the library (NOT the root directory of the ZIP archive!)
                # Note that the name of the root directory in Python zipfile module is a empty string.
                archive_root = None
                for p in z.namelist():
                    item_path = zipfile.Path(z, p)
                    if item_path.name != '' \
                            and item_path.is_dir() \
                            and item_path.parent.name == '':
                        if archive_root is not None:
                            logging.warning(
                                'Multiple directories found in the root directory. Ignoring those found later.')
                        else:
                            archive_root = item_path.name
                if archive_root is None:
                    logging.error('No directories found on the root directory.')
                    return None
                # Extract all the example sources
                filenames = z.namelist()
                example_sources = []
                for f in filenames:
                    m = re.fullmatch(r'^[^/]+/examples/((|.+/).+)/[^/]+[.](ino|pde|c|h|cpp|hpp|cxx|hxx|cc)$', f)
                    if m:
                        logging.debug('Found a source code: {}'.format(f))
                        found_example_name = m.group(1)
                        if examples is not None:
                            # Ignore example sources that is not specified with the argument.
                            if found_example_name not in examples:
                                continue
                        # Below is executed if the found example is one of the specified ones, or none is specified.
                        example_sources.append(str(os.path.relpath(Path(f), start=Path(archive_root, 'examples'))))
                res.append((
                    example_sources,
                    name,
                    version,
                    os.path.relpath(ar, start=Path(self.root_path, self.LIBRARY_STORAGE_DIRECTORY)),
                    archive_root))
        return res

    # examples is a list of (library_name, version, example_name) tuples.
    def extract_example_sketches(self, output_path, examples=None, version_flag=ALL_VERSIONS):
        extract_targets = self.compute_extract_targets(examples, version_flag)

        for (info, ex) in extract_targets:
            if ex is None:
                self.extract_examples_from_library(output_path, info)
            else:
                self.extract_examples_from_library(output_path, info, examples=ex)

    def extract_examples_from_library(self, output_path, info, examples=None):
        dataset_output_path = Path(output_path)
        if not dataset_output_path.exists():
            logging.debug('The library storage directory is not present. Creating one...')
            dataset_output_path.mkdir(0o755)
        target_library_path = Path(dataset_output_path, info.name)
        if not target_library_path.exists():
            logging.debug('The directory for the library is not present. Creating one...')
            target_library_path.mkdir(0o755)
        target_version_path = Path(target_library_path, info.version)
        if not target_version_path.exists():
            logging.debug('The directory for the version of the library is not present. Creating one...')
            target_version_path.mkdir(0o755)
        ar = list(info.path.glob('*.zip'))[0]
        try:
            z = ZipFile(ar)
        except BadZipFile as ex:
            logging.error('Invalid Zip archive: {}'.format(ar))
            logging.error('Description: {}'.format(str(ex.args[0])))
            return
        with z:
            # Extract all the example sources
            filenames = z.namelist()
            for f in filenames:
                m = re.fullmatch(r'^[^/]+/examples/((|.+/).+)/[^/]+[.](ino|pde|c|h|cpp|hpp|cxx|hxx|cc)$', f)
                if m:
                    logging.debug('Found a source code: {}'.format(f))
                    found_example_name = m.group(1)
                    if examples is not None:
                        # Ignore example sources that is not specified with the argument.
                        if found_example_name not in examples:
                            continue
                    # Below is executed if the found example is one of the specified ones, or none is specified.
                    target_source_path = Path(target_version_path, found_example_name)
                    if not target_source_path.exists():
                        logging.debug('The directory for the source code is not present. Creating one...')
                        target_source_path.mkdir(0o755, parents=True)
                    content = z.read(f)
                    with open(Path(target_source_path, Path(f).name), 'wb') as fo:
                        fo.write(content)

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

    # Restore missing library archives and update the library metadata.
    def restore_library(self, name, version, url):
        lib_storage_path = Path(self.root_path, self.LIBRARY_STORAGE_DIRECTORY)
        target_library_path = Path(lib_storage_path, name)
        target_version_path = Path(target_library_path, version)
        if self.is_downloaded(target_version_path):
            logging.info('The library archive in path: {} appears to be downloaded in the original Munin database. Restoring...')
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
