# SnipLink - Premium URL Shortener

SnipLink is a high-performance, full-stack URL shortener built with a FastAPI backend and an interactive, animated HTML/Tailwind CSS frontend powered by HTMX and GSAP.

## Tech Stack
- **Backend**: Python + FastAPI, SQLAlchemy (MySQL), Redis Cache, AWS DynamoDB (User Profiles), JWT Authentication, PyMySQL.
- **Frontend**: Plain HTML, Tailwind CSS (via CDN), HTMX (via CDN for form submissions & SPA-like feel), GSAP (via CDN for high-end micro-animations and toasts).

---

## Architecture Flow

1. **Authentication**: Users register and log in via secure forms. Passwords are encrypted using native `bcrypt`. Profiles are stored in **AWS DynamoDB**. Upon successful auth, a JWT token is returned and stored in the browser's `localStorage`.
2. **Redirection (Cache-Aside Pattern)**: When a visitor accesses `http://localhost:8000/{code}`:
   - The system checks **Redis** first. If hit, redirects in microseconds.
   - On cache miss, it queries **MySQL**. If found, it caches the mapping in Redis (1-hour TTL) and redirects.
   - If not found in either, a clean 404 is returned.
3. **Dashboard**: Fully protected. Automatically attaches the JWT token from `localStorage` as an `Authorization: Bearer <token>` header to all HTMX requests.

---

## How to Run Locally (Without Docker)

Follow these step-by-step instructions to run the application on your local machine.

### Prerequisites

You need the following services installed and running on your local machine:
1. **Python 3.11+**
2. **MySQL Database**: Ensure a database (default name: `url_shortener`) is created.
3. **Redis Server**: Default port `6379`.
4. **AWS DynamoDB**:
   - You can use a real AWS DynamoDB table (ensure your local machine has AWS credentials set up in `~/.aws/credentials` or configured via env variables).
   - Alternatively, you can run a local DynamoDB instance (e.g. via `localstack` or `amazon/dynamodb-local`) and specify its URL in `DYNAMODB_ENDPOINT_URL`.

---

### Step 1: Clone & Configure

1. Navigate to the project root directory:
   ```bash
   cd /Users/patelmaitry/Documents/URL
   ```

2. Copy the environment template file:
   ```bash
   cp .env.example .env
   ```

3. Open `.env` and fill in your actual service credentials:
   - Set your **MySQL** credentials (`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`).
   - Set your **Redis** credentials.
   - Set your **AWS** credentials and region (e.g., `us-east-1`). If using a local DynamoDB mock, set `DYNAMODB_ENDPOINT_URL=http://localhost:8000`.

---

### Step 2: Set Up Virtual Environment & Install Dependencies

1. Create a Python virtual environment:
   ```bash
   python3 -m venv venv
   ```

2. Activate the virtual environment:
   - **macOS/Linux**:
     ```bash
     source venv/bin/activate
     ```
   - **Windows**:
     ```cmd
     venv\Scripts\activate
     ```

3. Install the required libraries:
   ```bash
   pip install -r requirements.txt
   ```

---

### Step 3: Launch the Application

1. Start the FastAPI development server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
   *Note: On startup, FastAPI will automatically connect to MySQL and DynamoDB and create the necessary tables if they do not exist.*

2. Open your web browser and navigate to:
   ```
   http://localhost:8000
   ```
   *The entire frontend is served directly by the FastAPI backend for convenience!*

---

### Running the Test Suite

To verify the endpoints, authentication flows, database integrations, and caching logic, you can run the mock-based unit tests:
```bash
python3 -m unittest /Users/patelmaitry/.gemini/antigravity-ide/brain/fbc40259-55e0-426b-a963-7bf1611f77de/scratch/test_app.py
```
*(No running databases or Redis services are required to run this test suite as all connections are safely mocked!)*
