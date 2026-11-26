"""Connection to the Lakebase database bigbox_ops as the calling identity (OAuth, 1-hour token)."""

import psycopg
from databricks.sdk import WorkspaceClient

PROJECT = "projects/bigbox-ops"
BRANCH = f"{PROJECT}/branches/production"
ENDPOINT = f"{BRANCH}/endpoints/primary"
DATABASE = "bigbox_ops"


def connect(w: WorkspaceClient | None = None, autocommit: bool = True) -> psycopg.Connection:
    w = w or WorkspaceClient()
    host = w.postgres.get_endpoint(ENDPOINT).status.hosts.host
    token = w.postgres.generate_database_credential(endpoint=ENDPOINT).token
    user = w.current_user.me().user_name
    return psycopg.connect(
        host=host,
        dbname=DATABASE,
        user=user,
        password=token,
        sslmode="require",
        autocommit=autocommit,
    )
