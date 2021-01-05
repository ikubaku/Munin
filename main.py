# Munin - An Arduino Project code cloning detector: Database creator module
# 2020-2021 C ikubaku <hide4d51 at gmail.com>
# This program is licensed under The MIT License

import sys
import argparse
import logging
import datetime
import requests
import shutil
from pathlib import Path
import config
import library_index
import database
import analyzer
import util


def start_logging(log_path, verbosity, no_warning):
    print('Enabled logging to the log file.')
    logging.basicConfig(filename=log_path)
    # Temporarily increase log level to show mandatory messages
    logging.getLogger().setLevel(logging.INFO)
    logging.info('--- Start of the Munin log from date (UTC): {} ---'.format(datetime.datetime.utcnow()))
    if verbosity == 0:
        if no_warning:
            logging.getLogger().setLevel(logging.ERROR)
        else:
            logging.getLogger().setLevel(logging.WARNING)
    elif verbosity == 1:
        logging.getLogger().setLevel(logging.INFO)
    else:
        logging.getLogger().setLevel(logging.DEBUG)


def load_config(conf_path):
    logging.info('Reading the configuration from: {}...'.format(conf_path))
    return config.read_config(conf_path)


def initialize_command(args):
    if args.log is not None:
        start_logging(args.log, args.verbose, args.nowarn)
    return load_config(args.config)


def do_find_headers(conf):
    # Open the database
    logging.info('Opening the database...')
    db = database.Database(conf.database_root)
    db.load()

    # Create analyzer and look for library headers
    logging.info("Looking for libraries' header files...")
    an = analyzer.Analyzer(db, conf.temp_dir)
    an.find_headers()

    # Save the result
    logging.info('Saving the header dictionary...')
    db.save()

    return 0


def do_fetch(conf, populate=False):
    # Download the library index
    logging.info('Downloading the package index from: {}...'.format(conf.library_index_url))
    r = requests.get(conf.library_index_url)
    if r.status_code != 200:
        logging.error('Unexpected HTTP status code {} (expected 200).'.format(r.status_code))
        return -1
    index_access_date = datetime.datetime.now(datetime.timezone.utc)
    logging.info('Downloaded the index at: {}'.format(index_access_date))

    # Parse the library index
    logging.info('Parsing the library index...')
    try:
        index_json_dict = r.json()
    except ValueError:
        logging.error('The response does not contain valid JSON data.')
        return -1
    index = library_index.from_json_dict(index_json_dict)
    index.set_access_date(index_access_date)

    # Open and / or create the database
    logging.info('Opening the database...')
    db = database.Database(conf.database_root)

    # Fetch library archives and overwrite local data
    logging.info('Fetching library archives...')
    db.library_index = index
    db.download(overwrite=populate)

    # Save other important data
    logging.info('Saving additional data...')
    try:
        db.save()
    except IOError as e:
        logging.error('Something went wrong while writing the database: {}'.format(e))
        return -1

    return 0


def do_search(conf, heeader_name):
    # Open the database
    logging.info('Opening the database...')
    db = database.Database(conf.database_root)
    db.load()
    logging.info('Searching libraries for the header: {}...'.format(heeader_name))
    libs = db.search(heeader_name)
    if len(libs) == 0:
        print('No library is found.')
    else:
        print('Possibly corresponding libraries:')
        for lib in libs:
            print('name = {}, version = {}'.format(lib['name'], lib['version']))

    return 0


def do_search_examples(conf, header_names):
    # Open the database
    logging.info('Opening the database...')
    db = database.Database(conf.database_root)
    db.load()
    logging.info('Searching library examples for the header: {}...'.format(str(header_names)))
    res = db.search_example_sketches(header_names)
    print('Possibly corresponding library examples:')
    for r in res:
        print('name = {}, version = {}, example_name = {}'.format(r[0], r[1], r[2]))

    return 0


def do_guess_libraries(conf, sketch):
    with open(sketch) as f:
        logging.info('Parsing the given sketch...')
        headers = util.get_included_headers_from_source_code(f.read())
        return do_search_examples(conf, headers)


def do_extract(conf, output_path, sketch=None):
    # Open the database
    logging.info('Opening the database...')
    db = database.Database(conf.database_root)
    db.load()
    logging.info('Extracting example source codes...')
    if sketch is None:
        db.extract_example_sketches(output_path)
        return 0
    else:
        with open(sketch) as f:
            headers = util.get_included_headers_from_source_code(f.read())
            examples = db.search_example_sketches(headers)
            db.extract_example_sketches(output_path, examples=examples)
            return 0


def com_populate(args):
    conf = initialize_command(args)
    sys.exit(do_fetch(conf, populate=True))


def com_fetch(args):
    conf = initialize_command(args)
    sys.exit(do_fetch(conf))


def com_find_headers(args):
    conf = initialize_command(args)
    sys.exit(do_find_headers(conf))


def com_search(args):
    conf = initialize_command(args)
    if args.header is not None:
        sys.exit(do_search(conf, args.header))
    print('The header name is not specified.')
    sys.exit(-1)


def com_examples(args):
    conf = initialize_command(args)
    if args.headers is not None and len(args.headers) != 0:
        sys.exit(do_search_examples(conf, args.headers))
    print('The header names are not specified.')
    sys.exit(-1)


def com_guess(args):
    conf = initialize_command(args)
    if args.sketch is not None:
        sys.exit(do_guess_libraries(conf, args.sketch))
    print('The sketch is not specified.')
    sys.exit(-1)


def com_extract(args):
    conf = initialize_command(args)
    if args.output is None:
        print('The output location is not specified.')
        sys.exit(-1)
    if args.sketch is None:
        sys.exit(do_extract(conf, Path(args.output)))
    else:
        sys.exit(do_extract(conf, Path(args.output), Path(args.sketch)))


def main():
    parser = argparse.ArgumentParser(description='Munin - Code clone database creator')
    parser.add_argument('-c', '--config', help='configuration filename', default='munin.toml', metavar='CONFIG')
    parser.add_argument('-l', '--log', help='log file filename', metavar='LOG')
    parser.add_argument('-v', '--verbose', help='verbosity of the logging (max stack: 2)', action='count', default=0)
    parser.add_argument('-q', '--nowarn', help='suppress warning message (note that verbosity option overrides this)', action='store_true')
    command_parsers = parser.add_subparsers(help='Specify a subcommand', metavar='COMMAND')
    populate_parser = command_parsers.add_parser('populate', help='Create a database from the start. (overwrites any existing data)')
    populate_parser.set_defaults(func=com_populate)
    fetch_parser = command_parsers.add_parser('fetch', help='Look for the header candidates from the downloaded Arduino libraries.')
    fetch_parser.set_defaults(func=com_fetch)
    find_headers_parser = command_parsers.add_parser('find_headers', help='Upload the library index in the existing database.')
    find_headers_parser.set_defaults(func=com_find_headers)
    search_parser = command_parsers.add_parser('search', help='Find possibly corresponding libraries with a header file name.')
    search_parser.add_argument('header', help='Header file name for the searching.', metavar='HEADER')
    search_parser.set_defaults(func=com_search)
    search_example_parser = command_parsers.add_parser('examples', help='Look for example sketches with header file names.')
    search_example_parser.add_argument('headers', help='List of header file names for the searching.', nargs='*', metavar='HEADERS')
    search_example_parser.set_defaults(func=com_examples)
    guess_parser = command_parsers.add_parser('guess', help='Guess used libraries for the given sketch.')
    guess_parser.add_argument('sketch', help='The sketch filename.', metavar='SKETCH')
    guess_parser.set_defaults(func=com_guess)
    extract_parser = command_parsers.add_parser('extract', help='Create dataset for code clone detection.')
    extract_parser.add_argument('output',  help='The output location (directory)', metavar='DEST')
    extract_parser.add_argument('-s', '--sketch', help='The sketch file to narrow the dataset scale.', metavar='SKETCH')
    extract_parser.set_defaults(func=com_extract)
    args = parser.parse_args()

    if not shutil.rmtree.avoids_symlink_attacks:
        logging.warning('''Your system does not support the symlink attack mitigations for the shutil.rmtree function.
        Using this program is potentially dangerous because the attack can be used to remove arbitrary files in your 
        system. See Note in the Python documentation for more information:
        https://docs.python.org/3/library/shutil.html?highlight=shutil#shutil.rmtree''')

    try:
        args.func(args)
    except AttributeError:
        print('Bad command is specified or the command is empty.')
        sys.exit(-1)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
