"""PostgreSQL execution and catalog access. All generated SQL is read-only guarded upstream."""
import os
import psycopg2
from psycopg2.extras import RealDictCursor


class Database:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.getenv("DATABASE_URL") or "postgresql://{u}:{p}@{h}:{port}/{n}".format(
            u=os.getenv("DB_USER", "postgres"), p=os.getenv("DB_PASSWORD", "postgres"),
            h=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"), n=os.getenv("DB_NAME", "ecommerce_messy"))

    def execute(self, sql: str) -> list[dict]:
        with psycopg2.connect(self.dsn) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(row) for row in cur.fetchall()]

    def catalog(self) -> str:
        query = """SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns
        WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"""
        rows = self.execute(query)
        by_table = {}
        for row in rows:
            by_table.setdefault(row["table_name"], []).append(f'{row["column_name"]} {row["data_type"]}' + (" NULL" if row["is_nullable"] == "YES" else ""))
        return "\n".join(f"{table}({', '.join(columns)})" for table, columns in by_table.items())
