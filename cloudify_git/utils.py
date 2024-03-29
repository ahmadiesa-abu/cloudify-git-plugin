import os

from cloudify import ctx
from cloudify.utils import get_tenant_name
from cloudify.manager import get_rest_client
from cloudify.exceptions import NonRecoverableError
from cloudify_rest_client.exceptions import CloudifyClientError


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
