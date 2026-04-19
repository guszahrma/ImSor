# ImSor Web

Local web frontend for ImSor. Currently provides a duplicate image reviewer
with more features (annotations, etc.) coming soon.

## Prerequisites

1. Install Python 3.10 or newer from <https://www.python.org/downloads/>
   - During installation, check **Add Python to PATH**.
2. Open a terminal and navigate to the imsor-web folder:
   ```
   cd imsor-web
   ```
3. Create and activate a virtual environment:
   ```
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
4. Install dependencies:
   ```
   python -m pip install -r requirements.txt
   ```

## Configuration

Edit [`config.py`](config.py) before running:

| Setting    | Description                        | Default                 |
|------------|------------------------------------|-------------------------|
| `server_url` | URL of the Central Web Service   | `http://localhost:8000` |
| `username` / `password` | Credentials for an ImSor account | —            |
| `host`     | Address the local web server binds to | `127.0.0.1`         |
| `port`     | Port for the local web server      | `8080`                  |

## Usage

```
python server.py
```

Then open <http://localhost:8080> in your browser.

### Controls

| Action              | How                                 |
|---------------------|-------------------------------------|
| Next pair           | Click **Next** or press Right arrow |
| Previous pair       | Click **Previous** or press Left arrow |

## How it works

1. Fetches all unresolved duplicate pairs from the Central Web Service API.
2. For each pair, retrieves the image metadata (file path, etc.).
3. Serves actual image files directly from the local filesystem / network shares.
4. Displays both images side by side with their file paths above them.

## Important

- The Central Web Service and database must be running (`docker compose up`).
- Images must be accessible from the machine running this tool (e.g. network
  shares must be reachable).
