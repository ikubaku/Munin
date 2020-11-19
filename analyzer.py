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
        bar = Bar('PROGRESS', max=n_libs)
        for lib_info in self.database.get_library_info_list():
            headers = self.get_headers_for_library(lib_info.path)
            if headers is None:
                logging.warning('Analysis failed with the library: {}-{}'.format(lib_info.name, lib_info.version))
            else:
                self.database.add_header_dictionary_entry(lib_info, headers)
            bar.next()

    def get_headers_for_library(self, library_path):
        logging.info('Analyzing the library in path: {}...'.format(library_path))
        ar = list(library_path.glob('*.zip'))[0]
        with ZipFile(ar) as z:
            filenames = z.namelist()
            for f in filenames:
                if re.fullmatch(r'^[^/]+/library.properties$', f):
                    properties_path = f
                    break
                else:
                    properties_path = None
            if properties_path:
                props_bytes = z.read(properties_path)
                # Guess the encoding and try the most probable one
                guesser = UniversalDetector()
                guesser.feed(props_bytes)
                guess = guesser.close()
                if guesser.done:
                    encoding = guess['encoding']
                else:
                    # Fallback to the UTF-8 encoding
                    encoding = 'utf-8'
                try:
                    props_string = props_bytes.decode(encoding)
                except UnicodeError:
                    logging.warning('Could not decode the properties file properly for library in path:{}'.format(library_path))
                    return None
                # HACK: add a dummy section so that the Python's ConfigParser can parse the properties file
                props_string = '[properties]\n' + props_string
                parser = ConfigParser(interpolation=None)
                try:
                    parser.read_string(props_string)
                except configparser.Error:
                    logging.warning('Invalid library.properties file for library in path: {}'.format(library_path))
                    return None
                props = dict(dict(parser)['properties'])
                if 'includes' in props:
                    headers = props['includes'].split(',')
                    # Remove empty strings for trailing comma and empty include corner cases
                    headers = [x for x in headers if x != '']
                    return headers

            # Search in the source directory and the root directory of the library
            logging.info('The includes property is not present.')
            headers = []
            # Try the source directory
            for f in filenames:
                if re.fullmatch(r'^[^/]+/src/[^/]+.h$', f):
                    headers.append(str(Path(f).name))
            if len(headers) > 0:
                return headers
            # Try the root directory
            logging.info('No headers in the src directory.')
            logging.info('Trying the packages root directory...')
            for f in filenames:
                if re.fullmatch(r'^[^/]+/[^/]+.h$', f):
                    headers.append(str(Path(f).name))
            if len(headers) == 0:
                logging.warning('No header file found for the library with path: {}'.format(library_path))
            return headers

    # NOTE: Currently the temporary directory is unused
    def prepare_temp_dir(self):
        if self.temp_path.exists():
            shutil.rmtree(self.temp_path)
            self.temp_path.mkdir(0o755)
