import mysql.connector
from pymongo import MongoClient
from neo4j import GraphDatabase
# -------------------------
# CONFIG 
# -------------------------
MONGO_URI = "YOUR_URL"
NEO4J_URI = "YOUR_URL"
NEO4J_USER = "YOUR_USERNAME"
NEO4J_PASS = "YOUR_PASSWORD"

# ============ MySQL ============
def get_mysql_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="code_optimization_db"
    )

# ============ MongoDB ============
def get_mongo_db():
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=True
    )
    return client["codeopt"]

def get_execution_logs_collection():
    return get_mongo_db()["execution_logs"]

def get_optimization_logs_collection():
    return get_mongo_db()["optimization_logs"]

# ============ Neo4j ============
def get_neo4j_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASS)
    )

def test_connections():
    # MySQL
    conn = get_mysql_connection()
    conn.close()
    print("✅ MySQL connected")

    # MongoDB
    col = get_mongo_db()
    col["execution_logs"].insert_one({"test": "mongo_connection_ok"})
    print("✅ MongoDB connected")

    # Neo4j
    with get_neo4j_driver() as driver:
        driver.verify_connectivity()
        print("✅ Neo4j connected")

# test_connections()
