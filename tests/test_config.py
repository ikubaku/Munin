import unittest
import os
import config


class TestConfigurationParser(unittest.TestCase):
    def test_can_get_library_index_url(self):
        conf = config.read_config(os.path.join('samples', 'sample_config.toml'))
        self.assertEqual(conf.library_index_url, 'https://downloads.arduino.cc/libraries/library_index.json')

    def test_can_get_database_root(self):
        conf = config.read_config(os.path.join('samples', 'sample_config.toml'))
        self.assertEqual(conf.database_root, '~/munin')

    def test_can_get_temp_dir(self):
        conf = config.read_config(os.path.join('samples', 'sample_config.toml'))
        self.assertEqual(conf.temp_dir, '/tmp/munin')


if __name__ == '__main__':
    unittest.main()
