import duckdb
from .config import TRAINING_DB_PATH

def get_connection():
    """
    Single, canonical way to connect to the training DuckDB.
    Creating the file if it doesn't exist is fine (DuckDB does that).
    """
    return duckdb.connect(TRAINING_DB_PATH.as_posix())
