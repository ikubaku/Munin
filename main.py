# Munin - An Arduino Project code cloning detector: Database creator module
# 2020-2021 C ikubaku <hide4d51 at gmail.com>
# This program is licensed under The MIT License

import sys
import argparse
import logging
import datetime
import requests
import config
import library_index
import database


def do_populate(conf):
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
    db.download(overwrite=True)

    # Save other important data
    logging.info('Saving additional data...')
    try:
        db.save()
    except IOError as e:
        logging.error('Something went wrong while writing the database: {}'.format(e))
        return -1

    return 0


def do_find_headers(conf):
    # stub
    return 0


def main():
    parser = argparse.ArgumentParser(description='Munin - Code clone database creator')
    parser.add_argument('-c', '--config', help='configuration filename', default='munin.toml', metavar='CONFIG')
    parser.add_argument('-l', '--log', help='log file filename', metavar='LOG')
    parser.add_argument('command', choices=['populate', 'find_headers'], help='command to perform', metavar='COMMAND')
    args = parser.parse_args()

    if 'log' in vars(args):
        logging.basicConfig(filename=vars(args)['log'])

    # Load configuration
    conf_filename = vars(args)['config']
    logging.info('Reading the configuration from: {}...'.format(conf_filename))
    conf = config.read_config(conf_filename)

    command = vars(args)['command']
    if command == 'populate':
        return do_populate(conf)
    elif command == 'find_headers':
        do_find_headers(conf)
    else:
        logging.error('BUG: Unknown command: {}.'.format(command))
        return -1


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    sys.exit(main())

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
