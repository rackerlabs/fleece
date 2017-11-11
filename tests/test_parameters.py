import unittest

from fleece import parameters


class ParameterTests(unittest.TestCase):
    def check_config(self, config, flat_list, final_config):
        param_list = parameters._flatten_config(config)
        self.assertEqual(set(param_list), set(flat_list))
        new_config = parameters._unflatten_config(param_list)
        self.assertEqual(new_config, final_config)

    def test_flatten(self):
        self.check_config({
            'foo': 'bar',
            'pw': ':encrypt:baz'
        }, [
            ('/foo', 'bar', False),
            ('/pw', 'baz', True)
        ], {
            'foo': 'bar',
            'pw': 'baz'
        })
        self.check_config({
            'foo': {
                'a': 'b',
                'c': ':encrypt:d'
            },
            'pw': [
                '1',
                ':encrypt:2',
                '3'
            ]
        }, [
            ('/foo/a', 'b', False),
            ('/foo/c', 'd', True),
            ('/pw.0', '1', False),
            ('/pw.1', '2', True),
            ('/pw.2', '3', False)
        ], {
            'foo': {
                'a': 'b',
                'c': 'd'
            },
            'pw': [
                '1',
                '2',
                '3'
            ]
        })
        self.check_config({
            'foo': [
                {
                    'a': 'b'
                },
                {
                    'c': ':encrypt:d'
                }
            ]
        }, [
            ('/foo.0/a', 'b', False),
            ('/foo.1/c', 'd', True)
        ], {
            'foo': [
                {
                    'a': 'b'
                },
                {
                    'c': 'd'
                }
            ]
        })
        self.check_config({
            'foo': [
                {
                    'a': [
                        'b',
                        {
                            'c': 'd'
                        }
                    ]
                }
            ]
        }, [
            ('/foo.0/a.0', 'b', False),
            ('/foo.0/a.1/c', 'd', False)
        ], {
            'foo': [
                {
                    'a': [
                        'b',
                        {
                            'c': 'd'
                        }
                    ]
                }
            ]
        })
