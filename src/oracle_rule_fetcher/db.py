from collections.abc import Mapping
from dataclasses import dataclass

import oracledb

from oracle_rule_fetcher.models import Table

REQUIRED_ENV = ("ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_DSN")


class MissingEnvVarError(Exception):
    """Raised when a required database environment variable is missing."""


@dataclass
class DbSettings:
    user: str
    password: str
    dsn: str


def load_db_settings(env: Mapping[str, str]) -> DbSettings:
    missing = [key for key in REQUIRED_ENV if not env.get(key)]
    if missing:
        raise MissingEnvVarError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    return DbSettings(
        user=env["ORACLE_USER"],
        password=env["ORACLE_PASSWORD"],
        dsn=env["ORACLE_DSN"],
    )


class OracleClient:
    def __init__(self, settings: DbSettings):
        self.settings = settings
        self._conn = None

    def connect(self):
        self._conn = oracledb.connect(
            user=self.settings.user,
            password=self.settings.password,
            dsn=self.settings.dsn,
        )

    def cursor(self):
        if self._conn is None:
            self.connect()
        return self._conn.cursor()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def fetch_rows(cursor, sql: str, limit: int, params: dict | None = None) -> Table:
    if params is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, params)
    rows = cursor.fetchmany(limit)
    columns = [desc[0] for desc in cursor.description]
    return Table(columns=columns, rows=[list(row) for row in rows])
