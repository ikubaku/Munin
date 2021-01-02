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

    def analyze_libraries(self):
        self.find_headers()

    def find_headers(self):
        lib_info_list = self.database.get_library_info_list()
        n_libs = len(lib_info_list)
        print('Looking for library headers from {} libraries...'.format(n_libs))
        n_failure = 0
        bar = Bar('PROGRESS', max=n_libs)
        for lib_info in self.database.get_library_info_list():
            headers = self.get_headers_for_library(lib_info.path)
            if headers is None:
                logging.warning('Analysis failed with the library: {}-{}'.format(lib_info.name, lib_info.version))
                n_failure += 1
            else:
                self.database.add_header_dictionary_entry(lib_info, headers)
                example_headers = self.get_headers_in_examples(lib_info.path)
                if example_headers is None:
                    logging.warning('Analysis failed with the library: {}-{}'.format(lib_info.name, lib_info.version))
                    n_failure += 1
                else:
                    for (example_name, example_headers) in example_headers:
                        feature_headers = set(headers) & set(example_headers)
                        self.database.add_feature_database_entry(lib_info, example_name, feature_headers)
                if len(headers) == 0 and len(example_headers) != 0:
                    logging.warning('Found examples but the library has no header in its source directory.: {}-{}'.format(lib_info.name, lib_info.version))
            bar.next()
        bar.finish()
        if n_failure > 0:
            print()
            print('{} out of {} analyses failed. Consult the log file for more information.'.format(n_failure, n_libs))

    # returns None on failure
    def get_headers_for_library(self, library_path):
        logging.info('Analyzing the library in path: {}...'.format(library_path))
        ar = list(library_path.glob('*.zip'))[0]
        try:
            z = ZipFile(ar)
        except BadZipFile as ex:
            logging.warning('Invalid Zip archive: {}'.format(ar))
            logging.warning('Description: {}'.format(str(ex.args[0])))
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
            logging.info('No headers in the src directory.')
            logging.info('Trying the packages root directory...')
            for f in filenames:
                if re.fullmatch(r'^[^/]+/[^/]+[.](h|hpp)$', f):
                    headers.append(str(Path(f).name))
            if len(headers) == 0:
                logging.warning('No header file found for the library with path: {}'.format(library_path))
            return headers

    # returns None on failure
    def get_headers_in_examples(self, library_path):
        res = []
        logging.info('Analyzing the example sketches in path: {}...'.format(library_path))
        ar = list(library_path.glob('*.zip'))[0]
        try:
            z = ZipFile(ar)
        except BadZipFile as ex:
            logging.warning('Invalid Zip archive: {}'.format(ar))
            logging.warning('Description: {}'.format(str(ex.args[0])))
            return None
        with z:
            filenames = z.namelist()
            # Look for the example sketches
            sketches = []
            for f in filenames:
                if re.fullmatch(r'^[^/]+/examples/[^/]+/[^/]+[.](ino|pde)$', f):
                    sketches.append(f)
            if len(sketches) == 0:
                logging.warning('No example found for the library with path: {}'.format(library_path))
            for s in sketches:
                with z.open(s) as f:
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
                        sketch_source = data.decode(encoding)
                    except UnicodeError:
                        return None
                    headers = util.get_included_headers_from_source_code(sketch_source)
                    example_name = '.'.join(Path(s).name.split('.')[:-1])
                    res.append((example_name, headers))
        return res

    # NOTE: Currently the temporary directory is unused
    def prepare_temp_dir(self):
        if self.temp_path.exists():
            shutil.rmtree(self.temp_path)
            self.temp_path.mkdir(0o755)
