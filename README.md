# CodeOpt — Multi-Database Code Optimization Platform

A web application that lets you submit C, C++, and Python code, run it, apply GCC/G++ optimization flags, and analyze performance across executions. Built with a **three-database architecture**: MySQL for structured data, MongoDB for execution logs, and Neo4j for graph-based analytics.

---

## Features

### Core Execution
- Submit code via file upload or paste (C, C++, Python)
- Normal execution with output, runtime (ms), and binary size (KB)
- Optimized execution using GCC/G++ flags (`-O1`, `-O2`, `-O3`, `-Os`, etc.)
- Execution error logging: compile errors, runtime crashes, and timeouts

### Projects & Submissions
- Create and manage projects
- Multiple submissions per project
- Auto-named submissions via MySQL trigger if no name is given
- Full CRUD: update/delete projects, submissions, and user profile

### Analytics (MongoDB)
- Per-language average execution time
- Per-optimization-flag average speed and binary size
- Total run counts across all users

### Graph Features (Neo4j)
- **Best Optimization Finder** — ranks optimization profiles by speed for a submission or across an entire project
- **Recommendations** — suggests optimization profiles based on what similar users have used
- **Similar Submissions** — detects submissions with matching output and links them
- **Evolution Tracking** — shows how submissions in a project improved over time
- **Graph Analytics** — global graph statistics and relationship insights
- **Graph Visualizer** — interactive vis.js graph of User → Project → Submission → OptimizationProfile

### Authentication
- Register / Login / Logout
- Passwords hashed with `werkzeug.security`
- Session-based authentication

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Relational DB | MySQL 8 |
| Document Store | MongoDB Atlas |
| Graph DB | Neo4j (Aura or local) |
| PL/SQL | Stored procedures, functions, triggers (MySQL) |
| Frontend | Jinja2 templates, HTML/CSS |
| Graph UI | vis.js |

---

## Project Structure

```
codeopt/
├── app.py                  # Flask routes and code execution logic
├── db.py                   # Database connection helpers
├── mysql_ops.py            # All MySQL CRUD operations
├── mongodb_ops.py          # All MongoDB log operations
├── neo4j_ops.py            # All Neo4j graph operations
├── plsql.sql               # MySQL functions, stored procedures, triggers
├── exception.sql           # Exception handling additions + error log table
├── requirements.txt        # Python dependencies
└── templates/
    ├── base.html
    ├── home.html
    ├── index.html
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── profile.html
    ├── projects.html
    ├── submissions.html
    ├── run_result.html
    ├── opt_profiles.html
    ├── opt_result.html
    ├── logs.html
    ├── analytics.html
    ├── graph.html
    ├── graph_analytics.html
    ├── compare.html
    ├── best_opt.html
    ├── evolution.html
    ├── similar.html
    └── recommendations.html
```

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- MySQL 8.x
- MongoDB Atlas account (or local MongoDB)
- Neo4j Aura (or local Neo4j Desktop)
- GCC / G++ (via MSYS2 on Windows, or system package on Linux/macOS)

### 1. Clone the repository
```bash
git clone https://github.com/SwarnaDharshiniS/codeopt.git
cd codeopt
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure credentials

Copy `.env.example` to `.env` (or edit `db.py` directly) and fill in your values:

```
MONGO_URI=mongodb+srv://<user>:<pass>@cluster.mongodb.net/
NEO4J_URI=neo4j+s://<your-instance>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASS=<your-password>
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASS=root
MYSQL_DB=code_optimization_db
```

### 4. Set up MySQL schema
Run the SQL files in order:
```sql
-- 1. Create tables (run your schema DDL first)
-- 2. Run stored procedures and triggers
SOURCE plsql.sql;
-- 3. Add exception handling table and updated procedures
SOURCE exception.sql;
```

### 5. Configure compiler paths

Edit the paths near the top of `app.py` to match your system:
```python
PYTHON_PATH = r"C:\...\python.exe"   # or just "python3" on Linux/macOS
GCC_PATH    = r"C:\...\gcc.exe"       # or "gcc"
GPP_PATH    = r"C:\...\g++.exe"       # or "g++"
```

### 6. Run the application
```bash
python app.py
```

Visit `http://127.0.0.1:5000` in your browser.

---

## Database Schema (MySQL)

| Table | Purpose |
|---|---|
| `users` | Registered user accounts |
| `projects` | User-owned projects |
| `code_submissions` | Source code, language, input, last output |
| `optimization_profiles` | Named GCC/G++ flag profiles |
| `optimization_runs` | Results of optimized runs (upserted) |
| `execution_error_log` | Compile errors, runtime crashes, timeouts |

---
 developed as a DBMS course project.
