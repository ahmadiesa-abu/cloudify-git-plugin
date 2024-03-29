import os
import time
import shutil
import tempfile

from functools import wraps

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from .utils import get_local_deployment_dir


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
            # let's do some logic because might have this in so many ways
            # 1. file inside manager
            # 2. secret with keypair content
            final_git_keypair = git_keypair
            if isinstance(git_keypair, str):
                if git_keypair.startswith('-----BEGIN'):
                    if 'keypair_path' not in ctx.instance.runtime_properties:
                        # let's create temp file for this content
                        dep_dir = get_local_deployment_dir()
                        temp_file = tempfile.NamedTemporaryFile(
                            suffix='.pem', delete=False,
                            dir=os.path.dirname(dep_dir))
                        temp_file.write(git_keypair.encode('utf-8'))
                        temp_file.flush()
                        temp_file.close()
                        final_git_keypair = temp_file.name
                        os.chmod(final_git_keypair, 0o600)
                        ctx.instance.runtime_properties['keypair_path'] = \
                            final_git_keypair
                        original_ssh_key = os.path.expanduser('~/.ssh/id_rsa')
                        if os.path.isfile(original_ssh_key):
                            timestamp = int(time.time())
                            backup_ssh_key = f"{original_ssh_key}_{timestamp}"
                            shutil.move(original_ssh_key, backup_ssh_key)
                            ctx.instance.runtime_properties['keypair_bkp_path'] = \
                                backup_ssh_key
                            ctx.instance.runtime_properties['keypair_org_path'] = \
                                original_ssh_key
                        else:
                            ctx.instance.runtime_properties['keypair_org_path'] = \
                                'NA'
                            ctx.instance.runtime_properties['keypair_bkp_path'] = \
                                'NA'
                        shutil.copy(final_git_keypair, original_ssh_key)
                    else:
                        final_git_keypair = \
                            ctx.instance.runtime_properties['keypair_path']
                        original_file = \
                            ctx.instance.runtime_properties[
                                'keypair_org_path']
                        if original_file == 'NA':
                            original_file = os.path.expanduser('~/.ssh/id_rsa')
                        shutil.copy(final_git_keypair, original_file)
                elif not os.path.isfile(git_keypair):
                    raise NonRecoverableError(
                        f"file {git_keypair} not found on the system")
            kwargs['git_auth'] = {}#{"GIT_SSH_COMMAND": "ssh -i {}".format(final_git_keypair)}
        else:
            raise NonRecoverableError("No valid authentication data provided.")
        return func(*args, **kwargs)
    return operation(f, resumable=True)