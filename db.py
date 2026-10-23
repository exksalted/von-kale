import sqlite3

DB_PATH = "pp2_00.db"
SCHEMA_VERSION = 2


def init_schema(con):
    """Idempotent: creates missing tables/indexes and upgrades older DBs in place."""
    with con:
        con.execute("""CREATE TABLE IF NOT EXISTS records (
            Season TEXT, Rank INTEGER, Nick TEXT, Type TEXT, Lake TEXT, Date TEXT,
            Weight INTEGER, Lake_ID INTEGER, Fish_ID INTEGER,
            Percentile REAL, Score REAL, Out_Of INTEGER, Rarity REAL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS totalrecords
            (Season TEXT, Lake_ID INTEGER, Fish_ID INTEGER, Players INTEGER, Rarity REAL)""")
        # v2: unique keys. uq_records also covers (Season, Nick) lookups, so the old idx_rec is redundant.
        con.execute("DROP INDEX IF EXISTS idx_rec")
        con.execute("DROP INDEX IF EXISTS idx_tr")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_records ON records(Season, Nick, Lake_ID, Fish_ID)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_records_lake_fish ON records(Season, Lake_ID, Fish_ID)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_totals ON totalrecords(Season, Lake_ID, Fish_ID)")
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def connect(db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    init_schema(con)
    return con


def vacuum(con):
    """Shrinks the file after the delete/insert cycles. Must run outside a transaction."""
    con.execute("VACUUM")
  
