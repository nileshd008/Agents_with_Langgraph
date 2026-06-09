from fastmcp import FastMCP, Client
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import sqlite
from sqlalchemy import Table, MetaData, create_engine
from google.cloud.sql.connector import Connector
import sqlalchemy
from typing import List, Dict
# from pydantic import BaseModel, Field, validator
from typing import List, Dict
from decimal import Decimal
import os
import pandas as pd
from sqlalchemy import text
import json
from toon import encode, decode
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
from pydantic import BaseModel, Field, field_validator
mcp_server = FastMCP()
connector = Connector()
import urllib.parse
import sys
import logging
from dotenv import load_dotenv
load_dotenv()
CACHE_FILE = "mcp_session_dataframe.csv"


logging.basicConfig(
    filename="mcp_server_debug.txt",
    filemode="w",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("db_tools_server")
db_name = os.getenv('database_name')
username = os.getenv('username')
db_pass = urllib.parse.quote_plus(os.getenv('db_passward'))
connection_name = os.getenv('connection_name')

df = None
result = None

engine = create_engine(
    f"mysql+pymysql://{username}:{db_pass}@172.23.0.1:3306/{db_name}"
)

@mcp_server.tool
def greeting_tool(name: str):

    """Generates a personalized greeting.
    Args:
        name: name of the person to greet
    returns: 
        A greeting string

    """
    return f"Hello, Nice to meet you."


def get_sample_for_column(table_name):
    """Get sample data for each column in table"""
    try:
        with engine.connect() as connection:
            query = text(f"SELECT * FROM `{table_name}` LIMIT 10")
            df = pd.read_sql(query, connection)
        return df.to_dict(orient="records")
        
    except Exception as e:
        print(f"Error sampling table {table_name}: {e}")
        return []


@mcp_server.tool
def get_sql_table_schema() -> dict:
    '''Get get schema of all tables present in database'''
  
    table_scahema = {}

    inspector = sqlalchemy.inspect(engine)
    try:
        for table_name in inspector.get_table_names():
            if table_name.lower() == 'claims':
                samples = get_sample_for_column(table_name)
                columns = inspector.get_columns(table_name)
                pk = inspector.get_pk_constraint(table_name)
                fks = inspector.get_foreign_keys(table_name)

                table_scahema[table_name] = {
                    'columns': [
                        {
                            'name': col['name'],
                            'type': str(col['type']),
                            'nullable': col['nullable'],
                            'default': str(col['default']) if col['default'] else None
                        }
                        for col in columns
                    ],
                    'primary_key': pk.get('constrained_columns', []),
                    'foreign_keys': [
                        {
                            'columns': fk['constrained_columns'],
                            'referred_tables': fk['referred_table'],
                            'referred_columns': fk['referred_columns']
                        }
                        for fk in fks
                    ]
                }
                break
        return {'status': 'Success',
                'Error': None,
                'data': table_scahema
                }
    except Exception as e:
        return {'status': 'Fail',
                'Error': str(e),
                'data': None
                }



    
@mcp_server.tool
def validate_query(query: str) -> dict:
    """
    Validate Sql Query against databse without Fetching data.
    
    Args:
     query: Sql Query to check its valdity against database.
    
    Returns:

    """
    conn = engine.connect()

    try:
        sql_result = conn.execute(sqlalchemy.text(f"Explain {query}"))
        return {'status': 'SUCCESS', 'error': None, 'Query': query, 'result': sql_result}
    except Exception as e:
        return {'status': 'FAIL', 'error': str(e), 'Query': query, 'result': ''}



@mcp_server.tool
def get_sql_data(query: str) -> dict:
    """
    Executes a raw SQL query to fetch Information, statistics of sql query data.

    Args:
        query: The complete SQL query string to execute.
    
    Returns:
        Data information, stats and uniqueness of each column as output
    """
    from decimal import Decimal
    import json

    global df, result, engine
    try:

        with engine.connect() as conn:
            rows = conn.execute(sqlalchemy.text(query)).mappings().all()

        data = [
            {
                k: float(v) if isinstance(v, Decimal) else v
                for k, v in row.items()
            }
            for row in rows
        ]
        
        import copy
        df1 = pd.DataFrame(data)

        if df1.empty:
            return {
                "info": [],
                "description": {},
                "uniquness": {},
                "error": None
            }

        result = {
            "info": (
                df1.count()
                .to_frame("non_null")
                .assign(dtype=df1.dtypes.astype(str))
                .reset_index()
                .rename(columns={"index": "column"})
                .to_dict(orient="records")
            ),
            "description": df1.describe(include="all").fillna("").to_dict(),
            "uniquness": df1.nunique(dropna=False).to_dict(),
            "error": None,
        }

        return result
    
    except Exception as e:
        return {'info':'', 'description':'', 'uniquness':'', 'error': str(e)}

@mcp_server.tool
def execute_graph(query: str, graph_code: str):
    """Validate plotly visualization code using python.
    Args:
        query: sql query to extract data from database.
        graph_code : Pure Python code for Graph Generation. Assume a valid pandas DataFrame named 'df' is already available in the environment. Do not try to re-fetch the data or call other tools.
    Returns:
        status: Success or Fail
        Error: Error while generating Plotly graphs
        data: actual data
    """
    global df, result, engine
  
    with engine.connect() as conn:
        rows = conn.execute(sqlalchemy.text(query)).mappings().all()

    data = [
            {
                k: float(v) if isinstance(v, Decimal) else v
                for k, v in row.items()
            }
            for row in rows
        ]
    df = pd.DataFrame(data)
    graph_code = graph_code.strip()

    try:
        namespace = {'df': df, 'px': px, 'pd': pd}
        exec(graph_code, namespace)

        fig = namespace.get('fig')
    except Exception as e:
        return {'status': 'FAIL', 'Error': f'{e}', 'data': None}
    
    return {'status': 'SUCCESS', 'Error': None, 'data': pio.to_json(fig)}


if __name__=='__main__':
    mcp_server.run(transport = 'stdio')
