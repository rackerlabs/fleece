import sys
import pkg_resources

commands = ['build']


def main():
    if sys.argv[1] in commands:
        # if there is an extra with the name of this command, check that the
        # dependencies are installed before executing the command
        deps = pkg_resources.get_distribution('fleece')._dep_map.get(
            sys.argv[1], [])
        for dep in deps:
            try:
                __import__(dep.project_name)
            except ImportError:
                print('Dependency "{}" is not installed. Did you run '
                      '"pip install fleece[{}]"?'.format(dep, sys.argv[1]))
                sys.exit(1)

        # execute the command
        module = __import__('fleece.cli.' + sys.argv[1])
        module = getattr(module.cli, sys.argv[1])
        getattr(module, 'main')(sys.argv[2:])
    else:
        if sys.argv[1] not in ['--help', '-h']:
            print('"{}" is not an available fleece sub-command.'.format(
                sys.argv[1]))
        print('Available sub-commands: {}.'.format(', '.join(commands)))
        print('Use "fleece <sub-command> --help" for usage.')
