from pathlib import Path
import logging
import re
import shutil
from zipfile import ZipFile
from zipfile import BadZipFile
from progress.bar import Bar
from chardet.universaldetector import UniversalDetector

import util


class Analyzer:
    HEADERS_FILENAME = 'headers.toml'

    def __init__(self, db, temp_dir):
        self.database = db
        self.temp_path = Path(temp_dir)
        self.n_libraries = 0
        self.n_failed_libraries = 0
        self.n_example_sketches = 0
        self.n_failed_example_sketches = 0

    def analyze_libraries(self):
        self.find_headers()

    def find_headers(self):
        lib_info_list = self.database.get_library_info_list()
        self.n_libraries = len(lib_info_list)
        self.n_example_sketches = 0
        print('Looking for library headers from {} libraries...'.format(self.n_libraries))
        self.n_failed_libraries = 0
        bar = Bar('PROGRESS', max=self.n_libraries)
        for lib_info in self.database.get_library_info_list():
            headers = self.get_headers_for_library(lib_info.path)
            if headers is None:
                logging.error('Analysis failed with the library: {}-{}'.format(lib_info.name, lib_info.version))
                self.n_failed_libraries += 1
            else:
                self.database.add_header_dictionary_entry(lib_info, headers)
                (is_ok, example_headers) = self.get_headers_in_examples(lib_info.path)
                if not is_ok:
                    logging.error('Analysis failed with the library: {}-{}'.format(lib_info.name, lib_info.version))
                    self.n_failed_libraries += 1
                for (example_name, example_headers) in example_headers:
                    feature_headers = set(headers) & set(example_headers)
                    self.database.add_feature_database_entry(lib_info, example_name, feature_headers)
                if len(headers) == 0 and len(example_headers) != 0:
                    logging.warning(
                        'Found examples but the library has no header in its source directory.: {}-{}'
                        .format(lib_info.name, lib_info.version)
                    )
            bar.next()
        bar.finish()
        print()
        print('{} libraries and {} example sketches were processed.'.format(self.n_libraries, self.n_example_sketches))
        if self.n_failed_libraries > 0:
            print()
            print('{} libraries encountered errors during analysis.'.format(self.n_failed_libraries))
        if self.n_failed_example_sketches > 0:
            print()
            print('{} failure(s) reported while analysing example sketches.'.format(self.n_failed_example_sketches))
        if self.n_failed_libraries > 0 or self.n_failed_example_sketches > 0:
            print()
            print('To investigate reasons for these failures, consult the log file for more information.')

    # returns None on failure
    def get_headers_for_library(self, library_path):
        logging.info('Analyzing the library in path: {}...'.format(library_path))
        ar = list(library_path.glob('*.zip'))[0]
        try:
            z = ZipFile(ar)
        except BadZipFile as ex:
            logging.error('Invalid Zip archive: {}'.format(ar))
            logging.error('Description: {}'.format(str(ex.args[0])))
            return None
        with z:
            filenames = z.namelist()
            headers = []
            # Try the source directory
            for f in filenames:
                if re.fullmatch(r'^[^/]+/src/[^/]+[.](h|hpp)$', f):
                    headers.append(str(Path(f).name))
            if len(headers) > 0:
                return headers
            # Try the root directory
            logging.debug('No headers in the src directory.')
            logging.debug('Trying the packages root directory...')
            for f in filenames:
                if re.fullmatch(r'^[^/]+/[^/]+[.](h|hpp)$', f):
                    headers.append(str(Path(f).name))
            if len(headers) == 0:
                logging.info('No header file found for the library with path: {}'.format(library_path))
            return headers

    def get_example_sketches(self, filenames):
        # Look for the example sketches
        sketches = []
        for f in filenames:
            m = re.fullmatch(r'^[^/]+/examples/(|.+/)(.+)/\2[.](ino|pde)$', f)
            if m:
                logging.debug('Found a sketch with name: {}'.format(m.group(2)))
                sketches.append(f)
        return sketches

    def stringify_file_in_archive(self, zipfile, filename):
        with zipfile.open(filename) as f:
            data = f.read()
        guesser = UniversalDetector()
        guesser.feed(data)
        guess = guesser.close()
        if guesser.done:
            encoding = guess['encoding']
            if encoding is None:
                # try UTF-8 if we are not sure about the encoding
                encoding = 'utf-8'
        else:
            encoding = 'utf-8'
        try:
            res = data.decode(encoding)
        except UnicodeError:
            logging.error('Could not decode the example sketch with path: {}'.format(filename))
            res = None
        return res

    # returns (is_ok, res)
    def get_headers_in_examples(self, library_path):
        res = []
        is_failed = False
        logging.info('Analyzing the example sketches in path: {}...'.format(library_path))
        ar = list(library_path.glob('*.zip'))[0]
        try:
            z = ZipFile(ar)
        except BadZipFile as ex:
            logging.error('Invalid Zip archive: {}'.format(ar))
            logging.error('Description: {}'.format(str(ex.args[0])))
            return False, []
        with z:
            filenames = z.namelist()
            sketches = self.get_example_sketches(filenames)
            if len(sketches) == 0:
                logging.info('No example found for the library with path: {}'.format(library_path))
            self.n_example_sketches += len(sketches)
            for s in sketches:
                res_source = self.stringify_file_in_archive(z, s)
                if res_source is None:
                    self.n_failed_example_sketches += 1
                    is_failed = True
                else:
                    headers = util.get_included_headers_from_source_code(res_source)
                    # To get the example sketch name with separating directories, first we preceding library archive
                    # name and the examples directory name.
                    example_name = s[s.find('/examples/') + len('/examples/'):]
                    # and then, omit the actual sketch source code name.
                    example_name = '/'.join(example_name.split('/')[:-1])
                    res.append((example_name, headers))
        return not is_failed, res

    # NOTE: Currently the temporary directory is unused
    def prepare_temp_dir(self):
        if self.temp_path.exists():
            shutil.rmtree(self.temp_path)
            self.temp_path.mkdir(0o755)
