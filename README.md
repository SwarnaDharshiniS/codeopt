# 🚀 CodeOpt – Multi-Database Code Optimization Platform

## 📌 Overview

CodeOpt is a DBMS project that demonstrates the use of multiple databases (MySQL, MongoDB, Neo4j) to build a code execution and optimization analysis platform.

---

## 🏗️ Architecture

* **MySQL** → Users, Projects, Submissions (Relational Data)
* **MongoDB** → Execution Logs, Optimization Logs
* **Neo4j** → Graph Relationships, Recommendations, Analytics

---

## ⚙️ Features

### 👤 User Management

* User registration & login (hashed passwords)
* Profile management

### 📁 Project Management

* Create, update, delete projects
* Add submissions (code snippets)

### ▶️ Code Execution

* Supports:

  * Python
  * C
  * C++
* Execution tracking:

  * Execution time
  * Output
  * Errors (compile/runtime/timeout)

### ⚡ Optimization Engine

* Run code with optimization profiles
* Compare performance across flags
* Detect best optimization

### 📊 Analytics (MongoDB)

* Execution logs storage
* Average execution time per language
* Optimization performance metrics

### 🧠 Graph Features (Neo4j)

* Code evolution tracking
* Similar submissions detection
* Recommendation system
* Graph analytics dashboard

---

## 🛠️ Tech Stack

* Backend: Flask (Python)
* Databases:

  * MySQL
  * MongoDB
  * Neo4j
* Frontend: HTML + Jinja Templates

---

## 🚀 Setup Instructions

### 1. Clone repo

```bash
git clone https://github.com/yourusername/codeopt.git
cd codeopt
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure database

Update `db.py`:

```python
MONGO_URI = "your_mongo_uri"
NEO4J_URI = "your_neo4j_uri"
NEO4J_USER = "username"
NEO4J_PASS = "password"
```

### 4. Setup MySQL

* Create database: `code_optimization_db`
* Run SQL scripts:

  * `plsql.sql`
  * `exception.sql`

### 5. Run application

```bash
python app.py
```

---
