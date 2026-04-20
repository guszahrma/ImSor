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


5. Enable HTTPS
   To use Google OAuth, you need a signed certificate:

   a. For Local Development:
      To use Google OAuth and test HTTPS locally, you need a self-signed certificate:
      1. Open **Git Bash** in the `imsor-web` folder (the same folder as `server.py`).
      2. Run this command to generate a self-signed certificate (creates `cert.pem` and `key.pem`):
         ```bash
         openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
         ```
         You can press Enter for all prompts, or fill in as you wish.

## Google OAuth Setup

To enable Google login for ImSor Web:

1. Go to the Google Cloud Console: https://console.cloud.google.com/
2. Create OAuth 2.0 credentials for a Web Application.
3. Set the following:
   - **Authorized JavaScript origins:** `https://127.0.0.1:8080`
   - **Authorized redirect URIs:** `https://127.0.0.1:8080/login/google/authorized`
4. After creation, copy the Client ID and Client Secret.
5. Open `auto-annotator/credentials.py` in this repository.
6. Paste the values as follows:

   ```python
   GOOGLE_CLIENT_ID = "<your-client-id>"
   GOOGLE_CLIENT_SECRET = "<your-client-secret>"
   ```

**Do NOT commit your actual secret to public repositories.** The `credentials.py` file is gitignored for security.


## Configuration

Edit [`config.py`](config.py) before running:

| Setting    | Description                        | Default                 |
|------------|------------------------------------|-------------------------|
| `server_url` | URL of the Central Web Service   | `http://localhost:8000` |
| `username` / `password` | Credentials for an ImSor account | —            |
| `host`     | Address the local web server binds to | `127.0.0.1`         |
| `port`     | Port for the local web server      | `8080`                  |



## Start your Flask server:

   ```
   python server.py
   ```

   Visit `https://127.0.0.1:8080` (or your local IP and port). Your browser will warn about the self-signed certificate—this is expected for local development.

---

When deploying to production, use a real certificate (e.g., Let’s Encrypt) and a reverse proxy like nginx.

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
