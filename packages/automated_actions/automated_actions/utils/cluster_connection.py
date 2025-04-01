from dataclass import dataclass

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

from automated_actions.config import settings
from automated_actions.gql_definitions.tasks.clusters import query as clusters_query
from automated_actions.utils.gql_client import GQLClient
from automated_actions.utils.vault_client import VaultClient, VaultClientMissingArgsError, SecretFieldNotFoundError

@dataclass
class ClusterConnectionData:
    url: str
    token: str

def get_cluster_connection_data(cluster_name: str) -> ClusterConnectionData:
    gql_client = GQLClient(url=settings.qontract_server_url, token=qontract_server_token)
    cluster = clusters_query(gql_client.query, variables={"filter": {"name": cluster_name}})

    vault_client_args = {"server": settings.vault_server}
    if settings.vault_role_id:
        vault_client_args |= {"role_id": settings.vault_role_id, "secret_id": settings.vault_secret_id}
    else:
        # TODO: k8s auth
        raise VaultClientMissingArgsError


    vault_client = VaultClient(**vault_client_args)

    secret_path = cluster.automation_token.path
    field = cluster.automation_token.field
    server_token = vault.read_secret(path=secret_path).get(field)

    if not server_token:
        raise SecretFieldNotFoundError(f"{field} not found in secret {secret_path}")


    return ClusterConnectionData(url=cluster.server_url, token=token)

