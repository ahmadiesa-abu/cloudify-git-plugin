from functools import wraps

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError


def with_auth(func):
    @wraps(func)
    def f(*args, **kwargs):
        ctx = kwargs['ctx']
        credentials_config = ctx.node.properties.get('credentials_config', {})
        git_user = credentials_config.get('git_user', '')
        git_password = credentials_config.get('git_password', '')
        git_keypair = credentials_config.get('git_keypair', '')

        ctx.logger.info('Got these values for git_user {0} , git_password {1},'
                        ' git_keypair {2}'.format(git_user, '{0}{1}'.format(
                            git_password[:2], '*' * (len(git_password)-2)),
                            '{0}{1}'.format(git_keypair[:2],
                                            '*' * (len(git_keypair)-2))))
        if git_user and git_password:
            kwargs['git_auth'] = (git_user, git_password)
        elif git_keypair:
            kwargs['git_auth'] = {"GIT_SSH_COMMAND": "ssh -i {}".format(git_keypair)}
        else:
            raise NonRecoverableError("No valid authentication data provided.")
        return func(*args, **kwargs)
    return operation(f, resumable=True)