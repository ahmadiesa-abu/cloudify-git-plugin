import os

from git import exc, Repo, RemoteProgress

from cloudify import ctx
from cloudify.utils import get_tenant_name
from cloudify.manager import get_rest_client
from cloudify.exceptions import NonRecoverableError
from cloudify_rest_client.exceptions import CloudifyClientError

from .decorators import with_auth


@with_auth
def init_repo(ctx, **_):
    is_use_external = ctx.node.properties.get('use_external_resource', False)
    resource_config = ctx.node.properties['resource_config']
    repo_path = resource_config.get('repo_path')
    # if use_external true no need to init the repo as it would be already
    # initialized and configured correctly as well
    if not is_use_external and repo_path:
        repo = Repo.init(repo_path)
        if repo.bare:
            ctx.logger.info('Repository initialization successful.')
        else:
            raise NonRecoverableError('Failed to initialize the repository.')

    elif is_use_external:
        ctx.logger.debug('Skipping as use_external_resource True')
    else:
        raise NonRecoverableError('Invalid repo_path provided')


@with_auth
def clone_repo(ctx, git_auth, **_):

    def git_clone(source_path, tmp_path, kwargs):
        commit_hash = kwargs.pop('commit_hash', None)
        repo = Repo.clone_from(source_path, tmp_path, **kwargs)
        repo.git.submodule("update", "--init", "--recursive")
        if commit_hash:
            try:
                repo.git.checkout(commit_hash)
            except exc.GitCommandError as e:
                raise NonRecoverableError(f"Error checking out commit {commit_hash}: {e}")

    def get_deployment(deployment_id):
        try:
            rest_client = get_rest_client()
            return rest_client.deployments.get(deployment_id=deployment_id)
        except CloudifyClientError as e:
            if '404' in str(e):
                for deployment in rest_client.deployments.list(
                        _include=['id', 'display_name']):
                    if deployment.display_name == deployment_id:
                        return deployment
            return

    def get_local_deployment_dir():
        try:
            return ctx.local_deployment_workdir()
        except:
            deployment_name = deployment_name or ctx.deployment.id  # backward compat.
            deployments_old_dir = os.path.join('/opt', 'mgmtworker', 'work',
                                    'deployments',
                                    get_tenant_name(),
                                    deployment_name)

            deployments_new_dir = os.path.join('/opt', 'manager',
                                    'resources',
                                    'deployments',
                                    get_tenant_name(),
                                    deployment_name)

            if os.path.isdir(deployments_new_dir):
                return deployments_new_dir
            elif os.path.isdir(deployments_old_dir):
                return deployments_old_dir
            else:
                deployment = get_deployment(deployment_name)
                if deployment:
                    deployments_id_new_dir = os.path.join(
                        '/opt',
                        'manager',
                        'resources',
                        'deployments',
                        get_tenant_name(),
                        deployment.id)
                    if os.path.isdir(deployments_id_new_dir):
                        return deployments_id_new_dir

            raise NonRecoverableError("No deployment directory found!")

    class CloneProgress(RemoteProgress):
        def update(self, _, cur_count, max_count=None, message=''):
            if max_count is not None:
                ctx.logger.debug(f"Cloning: {cur_count}/{max_count}, {message}")
            else:
                ctx.logger.debug(f"Cloning: {cur_count}, {message}")

    is_use_external = ctx.node.properties.get('use_external_resource', False)
    resource_config = ctx.node.properties['resource_config']
    repo_path = resource_config.get('repo_path')
    repo_url = resource_config.get('repo_url')
    commit_id = resource_config.get('commit_id', None)
    debug_clone = resource_config.get('debug_clone', False)
    clone_kwargs = {}
    if debug_clone:
        clone_kwargs['progress'] = CloneProgress()
    else:
        clone_kwargs['progress'] = None
    if not repo_path:
        repo_path = get_local_deployment_dir()
    ctx.logger.info(f'clonning into {repo_path}')
    if git_auth:
        # user/pass
        if isinstance(git_auth, tuple):
            repo_url = repo_url.replace('http://', f'http://{git_auth[0]}:{git_auth[1]}@')
            repo_url = repo_url.replace('https://', f'https://{git_auth[0]}:{git_auth[1]}@')
        # keypair
        elif isinstance(git_auth, dict):
           clone_kwargs['env'] = git_auth
    if commit_id:
        clone_kwargs['commit_hash'] = commit_id
    # if use_external true , we are aussming we are cloning
    if is_use_external and repo_url and repo_path:
        try:
            git_clone(repo_url, repo_path, clone_kwargs)
        except exc.GitCommandError as e:
            if "Permission denied" in str(e):
                raise NonRecoverableError(
                    "User cfyuser might not have read permissions to "
                    "the private key or the key is not allowed to the repo"
                )
            elif 'Host key verification failed' in str(e):
                host_beginning = repo_url.index('@') + 1
                host_end = repo_url.index(':')
                host = repo_url[host_beginning: host_end]
                os.system("ssh-keyscan -t rsa {} >> ~/.ssh/known_hosts"
                        .format(host))
                git_clone(repo_url, repo_path, clone_kwargs)
            else:
                raise NonRecoverableError(e)

    elif not is_use_external:
        ctx.logger.debug('Skipping as use_external_resource False, which means we are initlizing a repo')
    else:
        raise NonRecoverableError('Invalid repo_path.repo_url provided')


@with_auth
def show_repo(ctx, **_):

    resource_config = ctx.node.properties('resource_config', {})
    repo_path = resource_config.get('repo_path')
    commit_id = resource_config.get('commit_id')

    if repo_path and commit_id:
        repo = Repo(repo_path)
        commit = repo.commit(commit_id)
        author = commit.author
        timestr = commit.authored_datetime.strftime('%c %z')
        msg = '\n'.join([
                f'commit {commit.hexsha}',
                f'Author: {author.name} <{author.email}>',
                f'Date:   {timestr}',
                '',
                commit.message
            ])
        ctx.logger.info('git show result {0}'.format(msg))
    else:
        raise NonRecoverableError('Invalid repo_path/commit_id provided')


@with_auth
def commit_repo(ctx, git_auth, **kwargs):
    pass


@with_auth
def rebase_repo(ctx, git_auth, **kwargs):
    pass