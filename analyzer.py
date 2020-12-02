from pathlib import Path
import logging
import re
import shutil
import configparser
from configparser import ConfigParser
from zipfile import ZipFile
from progress.bar import Bar
from chardet.universaldetector import UniversalDetector


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
            bar.next()
        if n_failure > 0:
            print()
            print('{} out of {} analyses failed. Consult the log file for more information.'.format(n_failure, n_libs))

    def get_headers_for_library(self, library_path):
        logging.info('Analyzing the library in path: {}...'.format(library_path))
        ar = list(library_path.glob('*.zip'))[0]
        with ZipFile(ar) as z:
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

    # NOTE: Currently the temporary directory is unused
    def prepare_temp_dir(self):
        if self.temp_path.exists():
            shutil.rmtree(self.temp_path)
            self.temp_path.mkdir(0o755)
