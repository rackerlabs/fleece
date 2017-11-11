import six
import boto3


def _flatten_config(config):
    """Creates a flat list of parameters from a configuration dictionary.
    Each element in the list is a tuple with (name, value, encrypted).

    Supported values are strings, nested dictionaries and nested lists. List
    values can be strings or nested dictionaries. Lists of lists are currently
    not supported.
    """
    param_list = []

    def flatten_item(data, key_prefix=''):
        if isinstance(data, six.text_type) or \
                isinstance(data, six.binary_type):
            encrypted = False
            if data.startswith(':encrypt:'):
                encrypted = True
                data = data[9:]
            param_list.append((key_prefix, data, encrypted))
        elif isinstance(data, list):
            i = 0
            for item in data:
                flatten_item(item, '{}.{}'.format(key_prefix, i))
                i += 1
        elif isinstance(data, dict):
            for k, v in data.items():
                flatten_item(v, key_prefix + '/' + k)

    flatten_item(config)
    return param_list


def _unflatten_config(param_list):
    """Reconstructs a config dictionary from a list of key/value tuples."""
    config = {}

    def parse_key(key):
        k = key
        i = -1
        if '.' in key:
            k, i = key.split('.')
            i = int(i)
        return k, i

    for param in param_list:
        keys = param[0].split('/')

        c = config
        for k in keys[1:-1]:
            key, index = parse_key(k)
            if key not in c:
                if index == -1:
                    c[key] = {}
                else:
                    c[key] = []
            c = c[key]
            if index != -1:
                while (len(c) < index + 1):
                    c.append(None)
                if c[index] is None:
                    c[index] = {}
                c = c[index]
        key, index = parse_key(keys[-1])
        if index == -1:
            c[key] = param[1]
        else:
            if key not in c:
                c[key] = []
            c = c[key]
            while (len(c) < index + 1):
                c.append(None)
            c[index] = param[1]

    return config


def read_parameters(root_path, **boto_args):
    """Read parameters from EC2 Parameter Store previously written with the
    write_parameters() function and return them as a configuration dictionary.
    """
    ssm = boto3.client('ssm', **boto_args)
    r = ssm.describe_parameters(ParameterFilters=[{
        'Key': 'Path',
        'Option': 'Recursive',
        'Values': [root_path]
    }])
    p = ssm.get_parameters(
        Names=[param['Name'] for param in r['Parameters']],
        WithDecryption=True)
    param_list = [(param['Name'], param['Value']) for param in p['Parameters']]
    return _unflatten_config(param_list)[root_path[1:]]


def erase_parameters(root_path, **boto_args):
    """Erase all parameters under the given path in the EC2 Parameter Store."""
    ssm = boto3.client('ssm', **boto_args)
    r = ssm.describe_parameters(ParameterFilters=[{
        'Key': 'Path',
        'Option': 'Recursive',
        'Values': [root_path]
    }])
    for param in r['Parameters']:
        ssm.delete_parameter(Name=param['Name'])


def write_parameters(config, kms_key, root_path, **boto_args):
    """Write a config file dictionary to the EC2 Parameter Store."""
    param_list = _flatten_config(config)
    ssm = boto3.client('ssm', **boto_args)

    # first remove old parameters
    r = ssm.describe_parameters(ParameterFilters=[{
        'Key': 'Path',
        'Option': 'Recursive',
        'Values': [root_path]
    }])
    for param in r['Parameters']:
        ssm.delete_parameter(Name=param['Name'])

    # write new parameters
    for param in param_list:
        if param[2]:
            ssm.put_parameter(Name=root_path + param[0], Value=param[1],
                              Type='SecureString', KeyId='alias/' + kms_key)
        else:
            ssm.put_parameter(Name=root_path + param[0], Value=param[1],
                              Type='String')
