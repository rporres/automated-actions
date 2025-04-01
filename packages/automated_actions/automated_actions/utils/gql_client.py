from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

from automated_actions.gql_definitions.tasks.clusters import query as clusters_query


class GQLClient:
    def __init__(self, url: str, retries: int = 3, token: str = "") -> None:
        req_headers = None
        if token:
            req_headers = {"Authorization": token}

        transport = RequestsHTTPTransport(url=url, retries=retries)
        self.client = Client(transport=transport, headers=req_headers)

    def query(self, query: str, variables: dict | None = None) -> dict[str, Any] | None:
        result = self.client.execute(
            gql(query), variables, get_execution_result=True
        ).formatted

        if "data" in result:
            return result["data"]

    def get_cluster_connection_data(cluster_name: str) -> ClusterConnectionData:
         cluster = clusters_query(
            self.query, variables={"filter": {"name": cluster_name}}
         )

