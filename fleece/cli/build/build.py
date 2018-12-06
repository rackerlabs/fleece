#!/usr/bin/env python
from __future__ import print_function

import argparse
from datetime import datetime
import hashlib
from io import BytesIO
import os
import subprocess
import sys
import tarfile
import tempfile

import docker
from docker import errors

build_dir = os.path.abspath(os.path.dirname(__file__))


def parse_args(args):
    parser = argparse.ArgumentParser(prog='fleece build',
                                     description='Simple Lambda builder.')
    parser.add_argument('--python36', '-3', action='store_true',
                        help='use Python 3.6 (default: Python 2.7)')
    parser.add_argument('--inject-build-info', action='store_true',
                        help='injects config.json into lambda, which contains '
                             'build time and version hash')
    parser.add_argument('--rebuild', action='store_true',
                        help='rebuild Python dependencies')
    parser.add_argument('--requirements', '-r', type=str,
                        default='',
                        help=('requirements.txt file with dependencies '
                              '(default: $service_dir/src/requirements.txt)'))
    parser.add_argument('--pipfile', '-p', type=str,
                        default='',
                        help=('directory containing Pipfile.lock '
                              '(default: $service_dir/Pipfile.lock)'))
    parser.add_argument('--dependencies', '-d', type=str, default='',
                        help='comma separated list of system dependencies')
    parser.add_argument('--target', '-t', type=str,
                        default='',
                        help=('target directory for lambda_function.zip '
                              '(default $service_dir/dist)'))
    parser.add_argument('--source', '-s', type=str,
                        default='',
                        help=('source directory to include in '
                              'lambda_function.zip (default: '
                              '$service_dir/src)'))
    parser.add_argument('--exclude', '-e', type=str, nargs='+',
                        help='glob pattern to exclude')
    parser.add_argument('service_dir', type=str,
                        help=('directory where the service is located '
                              '(default: $pwd)'))
    return parser.parse_args(args)


def get_version_hash():
    sha1 = os.environ.get('CIRCLE_SHA1', None)
    if sha1 is not None:
        return sha1

    try:
        sha1 = subprocess.check_output(
            'git log -1 | head -1 | cut -d" " -f2',
            shell=True,
        ).decode('utf-8').strip()
    except Exception as exc:
        print('Could not determine SHA1: {}'.format(exc))
        sha1 = None

    return sha1


def clean_up_container(container, clean_up_volumes=True):
    try:
        container.remove(v=clean_up_volumes)
    except docker.errors.APIError as e:
        if 'Failed to destroy btrfs snapshot' in str(e):
            # circle-ci builds do not get permissions that allow them to remove
            # containers, see https://circleci.com/docs/1.0/docker-btrfs-error/
            pass
        else:
            raise


def retrieve_archive(container, dist_dir):
    stream, stat = container.get_archive('/dist/lambda_function.zip')
    f = BytesIO()
    for chunk in stream:
        f.write(chunk)
    f.seek(0)
    with tarfile.open(fileobj=f, mode='r') as t:
        t.extractall(path=dist_dir)


def put_files(container, src_dir, path, single_file_name=None):
    stream = BytesIO()

    with tarfile.open(fileobj=stream, mode='w', dereference=True) as tar:
        if single_file_name:
            arcname = single_file_name
        else:
            arcname = os.path.sep
        tar.add(src_dir, arcname=arcname)
    stream.seek(0)
    container.put_archive(data=stream, path=path)


def create_volume(name):
    api = docker.from_env(version='auto')
    api.volumes.create(name)


def destroy_volume(name):
    api = docker.from_env(version='auto')
    try:
        volume = api.volumes.get(name)
    except errors.NotFound:
        return
    try:
        volume.remove()
    except docker.errors.APIError as exc:
        if '409 Client Error' in str(exc):
            print('Unable to remove volume - {}\n{}'.format(name, str(exc)))
        else:
            raise


def create_volume_container(image='alpine:3.4', command='/bin/true', **kwargs):
    api = docker.from_env(version='auto')
    api.images.pull(image)
    container = api.containers.create(
        image,
        command,
        **kwargs
    )
    return container


def build(args):
    python_version = 'python36' if args.python36 else 'python27'
    inject_build_info = args.inject_build_info
    service_dir = os.path.abspath(args.service_dir)
    service_name = os.path.basename(service_dir)

    if args.source:
        src_dir = os.path.abspath(args.source)
    else:
        src_dir = os.path.join(service_dir, 'src')
    if not os.path.exists(src_dir):
        print('Error: src directory not found!')
        sys.exit(1)

    if args.target:
        dist_dir = os.path.abspath(args.target)
    else:
        dist_dir = os.path.join(service_dir, 'dist')
    if not os.path.exists(dist_dir):
        os.makedirs(dist_dir)

    build_cache_dir = os.path.join(service_dir, 'build_cache')
    if not os.path.exists(build_cache_dir):
        os.makedirs(build_cache_dir)

    requirements_path = None
    pipfile = None
    if args.requirements:
        if args.pipfile:
            print('Error: `requirements` and `pipfile` are mutually exclusive')
            sys.exit(1)

        requirements_path = os.path.abspath(args.requirements)
    elif args.pipfile:
        pipfile = args.pipfile
    else:
        potential_req_file = os.path.join(service_dir, 'src/requirements.txt')
        potential_pipfile = os.path.join(service_dir, 'Pipfile.lock')

        if (os.path.exists(potential_pipfile) and
                not os.path.exists(potential_req_file)):
            pipfile = potential_pipfile
        else:
            if os.path.exists(potential_pipfile):
                print('Warning- Pipfile and requirements.txt were found. '
                      'Using requirements.txt. To use the Pipfile, specify '
                      '`--pipfile` or delete the requirements.txt file.')
            # don't worry; if requirements.txt isn't found an error will be
            # raised below
            requirements_path = potential_req_file

    dependencies = args.dependencies.split(',')

    if requirements_path:
        print(requirements_path)
        if not os.path.exists(requirements_path):
            print('Error: requirements file {} not found!'.format(
                requirements_path))
            sys.exit(1)
        _build(service_name=service_name,
               python_version=python_version,
               src_dir=src_dir,
               dependencies=dependencies,
               requirements_path=requirements_path,
               rebuild=args.rebuild,
               exclude=args.exclude,
               dist_dir=dist_dir,
               inject_build_info=inject_build_info)
    else:
        print(pipfile)
        if not os.path.exists(pipfile):
            print('Error: pipfile {} not found!'.format(pipfile))
            sys.exit(1)

        _build_with_pipenv(service_name=service_name,
                           python_version=python_version,
                           src_dir=src_dir,
                           dependencies=dependencies,
                           pipfile=pipfile,
                           rebuild=args.rebuild,
                           exclude=args.exclude,
                           dist_dir=dist_dir,
                           inject_build_info=inject_build_info)

        # If pipfile was specified, we need to write the requirements out
        # to a temporary directory.


def _build_with_pipenv(service_name, python_version, src_dir, pipfile,
                       dependencies, rebuild, exclude, dist_dir,
                       inject_build_info):
    requirements_path = None
    tmpdir = tempfile.mkdtemp()

    # it's too bad Python 2 doesn't have tempfile.TemporaryDirectory :(
    try:
        requirements_path = os.path.join(tmpdir, 'pipfile-requirements.txt')
        print('Creating temporary requirements.txt from Pipenv.lock...')
        requirements_txt_contents = subprocess.check_output(
            'pipenv lock -r',
            shell=True,
            cwd=os.path.dirname(pipfile))

        with open(requirements_path, 'w') as f:
            f.write(requirements_txt_contents)

        _build(service_name=service_name,
               python_version=python_version,
               src_dir=src_dir,
               requirements_path=requirements_path,
               dependencies=dependencies,
               rebuild=rebuild,
               exclude=exclude,
               dist_dir=dist_dir,
               inject_build_info=inject_build_info)
    finally:
        if requirements_path:
            try:
                os.remove(requirements_path)
            except OSError:
                pass
        os.rmdir(tmpdir)


def _build(service_name, python_version, src_dir, requirements_path,
           dependencies, rebuild, exclude, dist_dir, inject_build_info):
    print('Building {} with {}...'.format(service_name, python_version))

    try:
        docker_api = docker.from_env(version='auto')
    except:
        raise RuntimeError("Docker not found.")

    image, _logs = docker_api.images.build(
        path=build_dir, tag=service_name,
        buildargs={'python_version': python_version,
                   'deps': ' '.join(dependencies)})

    with open(requirements_path, 'rb') as fp:
        dependencies_sha1 = hashlib.sha1(fp.read()).hexdigest()

    # Set up volumes
    src_name = '{}-src'.format(service_name)
    req_name = '{}-requirements'.format(service_name)
    dist_name = '{}-dist'.format(service_name)
    create_volume(src_name)
    create_volume(req_name)
    create_volume(dist_name)

    src = create_volume_container(
        volumes=[
            '{}:/src'.format(src_name),
            '{}:/requirements'.format(req_name),
            '{}:/dist'.format(dist_name)]
    )

    # We want our build cache to remain over time if possible.
    build_cache_name = '{}-build_cache'.format(service_name)
    try:
        build_cache = docker_api.containers.get(build_cache_name)
    except errors.NotFound:
        create_volume(build_cache_name)
        build_cache = create_volume_container(
            name=build_cache_name,
            volumes=['{}:/build_cache'.format(build_cache_name)])

    # Inject our source and requirements
    put_files(src, src_dir, '/src')
    put_files(src, requirements_path, '/requirements',
              single_file_name='requirements.txt')

    # Environment variables (including any PIP configuration variables)
    environment = {'DEPENDENCIES_SHA': dependencies_sha1,
                   'VERSION_HASH': get_version_hash(),
                   'BUILD_TIME': datetime.utcnow().isoformat(),
                   'REBUILD_DEPENDENCIES': '1' if rebuild else '0',
                   'EXCLUDE_PATTERNS': ' '.join(
                       ['"{}"'.format(e) for e in exclude or []])}
    for var, value in os.environ.items():
        if var.startswith('PIP_'):
            environment[var] = value

    # Run Builder
    container = docker_api.containers.run(
        command=[
            '/docker_build_lambda.sh',
            'yes' if inject_build_info else ''
        ],
        image=image.tags[0],
        environment=environment,
        volumes_from=[src.id, build_cache.id],
        detach=True)
    for line in container.logs(stream=True, follow=True):
        sys.stdout.write(line.decode('utf-8'))
    status = container.wait()
    exit_code = status.get('StatusCode')
    error_msg = status.get('Error')

    if exit_code or exit_code is None:
        print('Error: build ended with exit code = '
              '{}\nError Message: {}.'.format(exit_code, error_msg))
    else:
        # Pull out our built zip
        retrieve_archive(container, dist_dir)

        # Clean up generated containers
        clean_up_container(container)
        clean_up_container(src)
        destroy_volume(dist_name)
        destroy_volume(req_name)
        destroy_volume(src_name)

        print('Build completed successfully.')
    sys.exit(exit_code)


def main(args):
    build(parse_args(args))
