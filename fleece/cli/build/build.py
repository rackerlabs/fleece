#!/usr/bin/env python
import argparse
from datetime import datetime
import hashlib
from io import BytesIO
import os
import subprocess
import sys
import tarfile

import docker
from docker import errors

build_dir = os.path.abspath(os.path.dirname(__file__))


def parse_args(args):
    parser = argparse.ArgumentParser(prog='fleece build',
                                     description='Simple Lambda builder.')
    parser.add_argument('--python36', '-3', action='store_true',
                        help='use Python 3.6 (default: Python 2.7)')
    parser.add_argument('--rebuild', action='store_true',
                        help='rebuild Python dependencies')
    parser.add_argument('--requirements', '-r', type=str,
                        default='',
                        help=('requirements.txt file with dependencies '
                              '(default: $service_dir/src/requirements.txt)'))
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
    raw_data = stream.read()
    f = BytesIO(raw_data)
    with tarfile.open(fileobj=f, mode='r') as t:
        t.extractall(path=dist_dir)


def put_files(container, src_dir, path, single_file_name=None):
    stream = BytesIO()

    with tarfile.open(fileobj=stream, mode='w') as tar:
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

    if args.requirements:
        requirements_path = os.path.abspath(args.requirements)
    else:
        requirements_path = os.path.join(service_dir, 'src/requirements.txt')
    print(requirements_path)
    if not os.path.exists(requirements_path):
        print('Error: requirements file {} not found!'.format(
            requirements_path))
        sys.exit(1)

    print('Building {} with {}...'.format(service_name, python_version))

    try:
        docker_api = docker.from_env(version='auto')
    except:
        raise RuntimeError("Docker not found.")

    image = docker_api.images.build(
        path=build_dir, tag=service_name,
        buildargs={'python_version': python_version,
                   'deps': ' '.join(args.dependencies.split(','))})

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

    # Run Builder
    container = docker_api.containers.run(
        image=image.tags[0],
        environment={'DEPENDENCIES_SHA': dependencies_sha1,
                     'VERSION_HASH': get_version_hash(),
                     'BUILD_TIME': datetime.utcnow().isoformat(),
                     'REBUILD_DEPENDENCIES': '1' if args.rebuild else '0'},
        volumes_from=[src.id, build_cache.id],
        detach=True)
    for line in container.logs(stream=True, follow=True):
        sys.stdout.write(line.decode('utf-8'))
    exit_code = container.wait()

    if exit_code:
        print('Error: build ended with exit code = {}.'.format(exit_code))
    else:
        # Pull out our built zip
        retrieve_archive(container, dist_dir)

        # Clean up generated containers
        clean_up_container(container)
        clean_up_container(src)

        print('Build completed successfully.')
    sys.exit(exit_code)


def main(args):
    build(parse_args(args))
