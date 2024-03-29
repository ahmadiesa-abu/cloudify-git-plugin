import os
import shutil
import zipfile

from git import exc, Repo, RemoteProgress

from cloudify import ctx
from cloudify.exceptions import NonRecoverableError

from .decorators import with_auth
from .utils import get_local_deployment_dir


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
        branch_name = kwargs.pop('branch_name', None)
        repo = Repo.clone_from(source_path, tmp_path, **kwargs)
        origin = repo.remote(name='origin')
        origin.fetch()
        for ref in origin.refs:
            if ref.remote_head != 'HEAD':
                repo.git.checkout('-B', ref.remote_head, ref)
        repo.git.fetch("--all")
        ctx.logger.debug(f'repo.branches {repo.branches}')
        if branch_name in repo.branches:
            repo.git.checkout(branch_name)
        else:
            raise NonRecoverableError(f"Branch '{branch_name}' does not exist in the repository.")
        repo.git.submodule("update", "--init", "--recursive")
        if commit_hash:
            try:
                repo.git.checkout(commit_hash)
            except exc.GitCommandError as e:
                raise NonRecoverableError(f"Error checking out commit {commit_hash}: {e}")

    def copy_repo_files(repo_dir, temp_dir):
        try:
            os.makedirs(temp_dir, exist_ok=True)
            for root, _, files in os.walk(repo_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, repo_dir)
                    destination_path = os.path.join(temp_dir, relative_path)
                    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                    shutil.copy(file_path, destination_path)
        except Exception as e:
            ctx.logger.error(f"Copying files from {repo_dir} to {temp_dir} failed: {str(e)}")

    def zip_repo(repo_dir, output_zip):
        try:
            ctx.logger.debug(f"zip_repo called with {repo_dir}, {output_zip}")
            temp_dir = os.path.join(os.path.dirname(repo_dir), 'temp_repo')
            copy_repo_files(repo_dir, temp_dir)
            with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, os.path.join(os.path.basename(repo_dir), relative_path))

            shutil.rmtree(temp_dir)
        except Exception as e:
            ctx.logger.error(f"zipping {repo_dir} failed due to : {str(e)}")

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
    # let's doctor git_user into repo
    git_user = ctx.node.properties['credentials_config'].get('git_user')
    if git_user and repo_url.startswith('https://github.com'):
        repo_url = \
            f"https://{git_user}@github.com/{repo_url.split('/')[-2]}" \
                f"/{repo_url.split('/')[-1]}"

    branch_name = resource_config.get('branch_name')
    commit_id = resource_config.get('commit_id', None)
    debug_clone = resource_config.get('debug_clone', False)
    clone_kwargs = {}
    if debug_clone:
        clone_kwargs['progress'] = CloneProgress()
    else:
        clone_kwargs['progress'] = None
    if not repo_path:
        repo_path = get_local_deployment_dir()
    ctx.instance.runtime_properties['repo_path'] = repo_path
    os.chdir(repo_path)
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
    if branch_name:
        clone_kwargs['branch_name'] = branch_name
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
        if git_auth and isinstance(git_auth, dict):
            # let's put back the original key after cloning
            temp_file = ctx.instance.runtime_properties['keypair_bkp_path']
            original_file = ctx.instance.runtime_properties['keypair_org_path']
            if original_file != 'NA':
                shutil.move(temp_file, original_file)
            else:
                os.remove(os.path.expanduser('~/.ssh/id_rsa'))
        path_to_archive = resource_config.get('path_to_archive')
        path_inside_repo = None
        if path_to_archive:
            path_inside_repo = f"{os.path.join(repo_path, path_to_archive)}.zip"
            zip_repo(path_to_archive, path_inside_repo)
        else:
            path_inside_repo = f"{repo_path}.zip"
            zip_repo(repo_path, path_inside_repo)
        ctx.instance.runtime_properties['archive_location'] = path_inside_repo
    elif not is_use_external:
        ctx.logger.debug('Skipping as use_external_resource False, which means we are initlizing a repo')
    else:
        raise NonRecoverableError('Invalid repo_path.repo_url provided')


def show_repo(ctx, **_):

    resource_config = ctx.node.properties['resource_config']
    repo_path = ctx.instance.runtime_properties['repo_path']
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


def delete_repo(ctx, **_):
    issues = []
    archive_location = ctx.instance.runtime_properties.get('archive_location', None)
    if archive_location:
        try:
            os.remove(archive_location)
        except Exception as e:
            ctx.logger.error(f"deleting {archive_location} failed due to : {str(e)}")
    else:
        issues.append('Invalid archive_location provided')
    keypair_path = ctx.instance.runtime_properties.get('keypair_path', None)
    if keypair_path:
        try:
            os.remove(keypair_path)
        except Exception as e:
            ctx.logger.error(f"deleting {keypair_path} failed due to : {str(e)}")
    else:
        issues.append('Invalid keypair_path provided')

    if issues:
        issues_str = '\n'.join(issues)
        raise NonRecoverableError(f"{issues_str}")
