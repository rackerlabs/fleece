import os
import shutil
import tempfile
import unittest

import six

from fleece.cli.build import build

if six.PY2:
    import mock
    from StringIO import StringIO
else:
    from unittest import mock
    from io import StringIO


class TestBuildDispatchesToCorrectFunction(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.patcher1 = mock.patch('fleece.cli.build.build._build')
        self.patcher2 = mock.patch('fleece.cli.build.build._build_with_pipenv')
        self.mock_build = self.patcher1.start()
        self.mock_build_with_pipenv = self.patcher2.start()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        self.patcher2.stop()
        self.patcher1.stop()

    def rel_path(self, path):
        """Returns path to something in tmpdir."""
        return os.path.join(self.tmpdir, path)

    def make_file(self, path, content):
        with open(self.rel_path(path), 'w') as f:
            f.write(content)

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_build_with_bad_src_directory(self, stdout):
        with self.assertRaises(SystemExit):
            args = build.parse_args([self.tmpdir])
            build.build(args)

        self.mock_build_with_pipenv.assert_not_called()
        self.assertEqual(stdout.getvalue(),
                         'Error: src directory not found!\n')

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_build_with_bad_explicit_src_directory(self, stdout):
        with self.assertRaises(SystemExit):
            args = build.parse_args([
                self.tmpdir, '--source', os.path.join(self.tmpdir, 'src')
            ])
            build.build(args)

        self.mock_build_with_pipenv.assert_not_called()
        self.assertEqual(stdout.getvalue(),
                         'Error: src directory not found!\n')

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_build_with_missing_requirements_file(self, stdout):
        os.makedirs(self.rel_path('src'))
        requirements_file = self.rel_path('src/requirements.txt')
        with self.assertRaises(SystemExit):
            args = build.parse_args([
                self.tmpdir
            ])
            build.build(args)

        self.assertEqual(stdout.getvalue(),
                         '{0}\nError: requirements file {0} not found!\n'
                         .format(requirements_file))

        self.mock_build_with_pipenv.assert_not_called()
        self.mock_build.assert_not_called()

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_by_default_use_requirements_file(self, stdout):
        os.makedirs(self.rel_path('src'))
        self.make_file('src/requirements.txt', '')

        args = build.parse_args([
            self.tmpdir
        ])
        build.build(args)

        self.mock_build_with_pipenv.assert_not_called()
        self.mock_build.assert_called_once()
        self.mock_build.assert_called_with(
            service_name=os.path.basename(self.tmpdir),
            python_version='python27',
            src_dir=self.rel_path('src'),
            requirements_path=self.rel_path('src/requirements.txt'),
            dependencies=[''],
            rebuild=False,
            dist_dir=self.rel_path('dist'),
        )

        # It creates a few directories...
        self.assertTrue(os.path.exists(self.rel_path('dist')))
        self.assertTrue(os.path.exists(self.rel_path('build_cache')))

        self.assertEqual(stdout.getvalue(),
                         '{}\n'.format(self.rel_path('src/requirements.txt')))

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_by_use_requirements_file_if_both_are_found(self, stdout):
        os.makedirs(self.rel_path('src'))
        self.make_file('src/requirements.txt', '')
        self.make_file('Pipfile.lock', '')

        args = build.parse_args([
            self.tmpdir
        ])
        build.build(args)

        self.mock_build_with_pipenv.assert_not_called()
        self.mock_build.assert_called_once()
        self.mock_build.assert_called_with(
            service_name=os.path.basename(self.tmpdir),
            python_version='python27',
            src_dir=self.rel_path('src'),
            requirements_path=self.rel_path('src/requirements.txt'),
            dependencies=[''],
            rebuild=False,
            dist_dir=self.rel_path('dist'),
        )

        # It creates a few directories...
        self.assertTrue(os.path.exists(self.rel_path('dist')))
        self.assertTrue(os.path.exists(self.rel_path('build_cache')))

        self.assertEqual(stdout.getvalue(),
                         'Warning- Pipfile and requirements.txt were found. '
                         'Using requirements.txt. To use the Pipfile, specify '
                         '`--pipfile` or delete the requirements.txt file.\n'
                         '{}\n'.format(self.rel_path('src/requirements.txt')))

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_use_specified_target_directory(self, stdout):
        os.makedirs(self.rel_path('src'))
        self.make_file('src/requirements.txt', '')

        args = build.parse_args([
            self.tmpdir, '--target', self.rel_path('crazy-dist')
        ])
        build.build(args)

        self.mock_build_with_pipenv.assert_not_called()
        self.mock_build.assert_called_once()
        self.mock_build.assert_called_with(
            service_name=os.path.basename(self.tmpdir),
            python_version='python27',
            src_dir=self.rel_path('src'),
            requirements_path=self.rel_path('src/requirements.txt'),
            dependencies=[''],
            rebuild=False,
            dist_dir=self.rel_path('crazy-dist'),
        )

        # Make sure it creates the path.
        self.assertTrue(os.path.exists(self.rel_path('crazy-dist')))

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_use_specified_requirements_file(self, stdout):
        os.makedirs(self.rel_path('src'))
        self.make_file('wacky-requirements.txt', '')

        args = build.parse_args([
            self.tmpdir,
            '--requirements', self.rel_path('wacky-requirements.txt')
        ])
        build.build(args)

        self.mock_build_with_pipenv.assert_not_called()
        self.mock_build.assert_called_once()
        self.mock_build.assert_called_with(
            service_name=os.path.basename(self.tmpdir),
            python_version='python27',
            src_dir=self.rel_path('src'),
            requirements_path=self.rel_path('wacky-requirements.txt'),
            dependencies=[''],
            rebuild=False,
            dist_dir=self.rel_path('dist'),
        )

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_use_specified_requirements_and_pipfile_fails(self, stdout):
        os.makedirs(self.rel_path('src'))
        self.make_file('wacky-requirements.txt', '')

        with self.assertRaises(SystemExit):
            args = build.parse_args([
                self.tmpdir,
                '--requirements', self.rel_path('wacky-requirements.txt'),
                '--pipfile', self.rel_path('wacky-pipfile')
            ])
            build.build(args)

        self.assertEqual(stdout.getvalue(),
                         'Error: `requirements` and `pipfile` are mutually '
                         'exclusive\n')

        self.mock_build_with_pipenv.assert_not_called()
        self.mock_build.assert_not_called()

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_fails_is_pipfile_missing(self, stdout):
        os.makedirs(self.rel_path('src'))

        with self.assertRaises(SystemExit):
            args = build.parse_args([
                self.tmpdir,
                '--pipfile', self.rel_path('wacky-pipfile')
            ])
            build.build(args)

        self.assertEqual(stdout.getvalue(),
                         '{0}\nError: pipfile {0} not found!\n'.format(
                         self.rel_path('wacky-pipfile')))

        self.mock_build_with_pipenv.assert_not_called()
        self.mock_build.assert_not_called()

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_uses_valid_pipfile_missing(self, stdout):
        os.makedirs(self.rel_path('src'))
        self.make_file('wacky-pipfile', '')

        args = build.parse_args([
            self.tmpdir,
            '--pipfile', self.rel_path('wacky-pipfile')
        ])
        build.build(args)

        self.mock_build.assert_not_called()
        self.mock_build_with_pipenv.assert_called_once()
        self.mock_build_with_pipenv.assert_called_with(
            service_name=os.path.basename(self.tmpdir),
            python_version='python27',
            src_dir=self.rel_path('src'),
            pipfile=self.rel_path('wacky-pipfile'),
            dependencies=[''],
            rebuild=False,
            dist_dir=self.rel_path('dist'),
        )


class TestBuildWithPipenv(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.patcher1 = mock.patch('fleece.cli.build.build._build')
        self.requirements_txt_contents = 'requirements_txt_contents'
        self.patcher2 = mock.patch('subprocess.check_output',
                                   return_value=self.requirements_txt_contents)
        self.mock_build = self.patcher1.start()
        self.mock_sp = self.patcher2.start()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        self.patcher2.stop()
        self.patcher1.stop()

    def rel_path(self, path):
        """Returns path to something in tmpdir."""
        return os.path.join(self.tmpdir, path)

    def make_file(self, path, content):
        with open(self.rel_path(path), 'w') as f:
            f.write(content)

    @mock.patch('sys.stdout', new_callable=StringIO)
    def test_happy_path(self, stdout):
        self.make_file('Pipenv.lock', '')

        expected_kwargs = {
            'service_name': 'service_name',
            'python_version': 'python_version',
            'src_dir': 'src_dir',
            'dependencies': ['deps'],
            'rebuild': True,
            'dist_dir': 'dist_dir'
        }

        build_state = {}

        def on_build(**kwargs):
            r_p = kwargs.pop('requirements_path')
            self.assertEquals(kwargs, expected_kwargs)
            # This will be in a random directory created by _build_with_pipenv
            self.assertTrue(r_p.endswith('/pipfile-requirements.txt'))
            self.assertTrue(os.path.exists(r_p))
            # Make sure it wrote what the mock subprocess call gave it
            with open(r_p) as f:
                self.assertEqual(f.read(), self.requirements_txt_contents)
            build_state['requirements_path'] = r_p

        self.mock_build.side_effect = on_build

        # In case it isn't obvious, all we need to test here is that this
        # function forwards every argument to `_build`
        build._build_with_pipenv(
            pipfile=self.rel_path('Pipenv.lock'),
            **expected_kwargs)

        self.mock_build.assert_called_once()

        # make sure it deleted the directory it created
        self.assertFalse(os.path.exists(build_state['requirements_path']))
