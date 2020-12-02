# Munin - An Arduino Project code cloning detector: Database creator module
# 2020-2021 C ikubaku <hide4d51 at gmail.com>
# This program is licensed under The MIT License

import sys
import argparse
import logging
import datetime
import requests
import shutil
import config
import library_index
import database
import analyzer


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


def main():
    parser = argparse.ArgumentParser(description='Munin - Code clone database creator')
    parser.add_argument('-c', '--config', help='configuration filename', default='munin.toml', metavar='CONFIG')
    parser.add_argument('-l', '--log', help='log file filename', metavar='LOG')
    parser.add_argument('command', choices=['populate', 'find_headers', 'fetch'], help='command to perform', metavar='COMMAND')
    args = parser.parse_args()

    if 'log' in vars(args):
        logging.basicConfig(filename=vars(args)['log'])

    if not shutil.rmtree.avoids_symlink_attacks:
        logging.warning('''Your system does not support the symlink attack mitigations for the shutil.rmtree function.
        Using this program is potentially dangerous because the attack can be used to remove arbitrary files in your 
        system. See Note in the Python documentation for more information:
        https://docs.python.org/3/library/shutil.html?highlight=shutil#shutil.rmtree''')

    # Load configuration
    conf_filename = vars(args)['config']
    logging.info('Reading the configuration from: {}...'.format(conf_filename))
    conf = config.read_config(conf_filename)

    command = vars(args)['command']
    if command == 'populate':
        # populate: Create a database from the start. (overwrites any existing data)
        return do_fetch(conf, populate=True)
    elif command == 'find_headers':
        # find_headers: Look for the header candidates from the downloaded Arduino libraries.
        do_find_headers(conf)
    elif command == 'fetch':
        # fetch: Upload the library index in the existing database.
        do_fetch(conf)
    else:
        logging.error('BUG: Unknown command: {}.'.format(command))
        return -1


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    sys.exit(main())

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
