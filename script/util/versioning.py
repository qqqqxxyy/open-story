"""One release policy; persistent compatibility is checked at the data boundary."""
from .runtime import current
from .errors import ContractError


def version_policy(settings=None):
    settings = current().settings if settings is None else settings
    release = settings['skill_version']
    minimum = settings['version_compatibility']['minimum_supported']
    if type(release) is not int or type(minimum) is not int or not 0 < minimum <= release:
        raise ContractError('CONFIGURATION_ERROR', 'Invalid global version compatibility policy')
    return {'current': release, 'minimum_supported': minimum}


def current_version():
    return version_policy()['current']


def validate_version(value, policy=None, subject='database'):
    policy = version_policy() if policy is None else policy
    if type(value) is not int or not policy['minimum_supported'] <= value <= policy['current']:
        raise ContractError('VERSION_UNSUPPORTED',
            f"Unsupported {subject} version {value!r}; supported skill releases "
            f"{policy['minimum_supported']}..{policy['current']}")
    return value
