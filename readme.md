# ImSor

ImSor is short for **image sorter**.

The intention is for it to:

- Search my local network for images I have distributed on different computers and servers.
- Identify duplicate candidates.
- Allow presentation of duplicate candidates for human-made decision if either can be removed.
- Help me annotate images based on:
  - when they were taken
  - what is on the image
  - where images were taken
  - …
- Have the possibility to allow people in the images to veto or allow that they are shared with other users.
- Have support for creating webpage slide shows based on annotation.
- Allow moving the image files to better locations.
- Annotation of images (identify who is in which image):
  - manually by users
  - automated by AI-like modules.

## Architecture

The system consists of four components, all Python-based.

### 1. Central Web Service (Docker on Asustor NAS)

- **Framework:** Python + FastAPI
- Provides a REST API that all other components communicate with.
- Serves the Web Frontend.
- Manages user accounts, image metadata, annotations, duplicate tracking, and sharing permissions.

### 2. Database (Docker on Asustor NAS)

- PostgreSQL running in a separate Docker container on the Asustor NAS.
- Stores all persistent data: image metadata, checksums, EXIF data, annotations,
  user accounts, face embeddings, duplicate pairs, sharing/veto decisions.

### 3. Scanner Agent (Windows machines)

- Python script/service that runs on each Windows machine that has images to index.
- Scans configured folders for images.
- Calculates checksums for duplicate detection.
- Reads EXIF metadata (date taken, GPS coordinates, camera info, etc.).
- Reports discovered image metadata to the Central Web Service via its REST API.

### 4. AI Service (Windows machine with sufficient hardware)

- Python service running on a machine with enough processing power for AI workloads.
- Uses local AI models for face detection, body detection, and face recognition.
- Pulls un-analyzed images from the Central Web Service, processes them, and pushes results back.
- Learns to recognize previously annotated persons over time using face embeddings.
- Can be dockerized if performance allows.

### Data Flow

- Scanner Agent(s) discover images and report metadata to the Central Web Service.
- AI Service pulls unprocessed images from the Central Web Service, analyzes them, and returns results.
- Users interact through the Web Frontend to browse, annotate, review duplicates, manage sharing, and create slideshows.

## Supporting Tools

Standalone utilities used alongside the main system.

| Tool | Description | Details |
|------|-------------|---------|
| [scanner-agent](scanner-agent/) | Scans folders on Windows machines for images, extracts EXIF metadata and checksums, and reports them to the Central Web Service. Detects changes on re-scan. | [scanner-agent/readme.md](scanner-agent/readme.md) |
| [exif-extractor](exif-extractor/) | Extracts all EXIF metadata from an image file and writes it to a JSON file. Useful for inspecting what tags are available in your photos. | [exif-extractor/readme.md](exif-extractor/readme.md) |

## Developer Setup

### Prerequisites

1. **Install Docker Desktop**
   - Download from <https://www.docker.com/products/docker-desktop/>
   - Run the installer and follow the prompts.
   - On Windows, Docker Desktop requires WSL 2 (Windows Subsystem for Linux).
     The installer will prompt you to enable it if not already active.
   - After installation, restart your computer if prompted.
   - Open Docker Desktop and wait for it to say "Docker Desktop is running".

2. **Install Git** (if not already installed)
   - Download from <https://git-scm.com/downloads>

### Running the Central Web Service + Database

The system uses two Docker containers managed by docker-compose:

| Container    | Role                        |
|--------------|-----------------------------|
| `imsor-db`   | PostgreSQL 16 database      |
| `imsor-web`  | FastAPI web service (Python) |

Steps:

1. Open a terminal and navigate to the ImSor project root directory.
2. Run:
   ```
   docker compose up --build
   ```
   This will:
   - Build the FastAPI web service container from `central-service/Dockerfile`.
   - Pull the PostgreSQL 16 image (first time only).
   - Start both containers.
3. Wait until you see log output indicating the web service is running.
4. Open a browser and go to:
   - <http://localhost:8000> — should return a JSON status message.
   - <http://localhost:8000/docs> — interactive API documentation (Swagger UI).

### First-Time Setup (Creating the Admin Account)

When running the system for the first time (empty database), you must create
an admin account before you can use the API.

1. Open the Swagger UI at <http://localhost:8000/docs>
2. **Verify setup is needed:**
   - Expand `GET /setup/status` and click "Try it out", then "Execute".
   - If `setup_complete` is `false`, proceed to step 3.
3. **Create the admin account:**
   - Expand `POST /setup/` and click "Try it out".
   - Fill in the request body:
     ```json
     {
       "username": "admin",
       "display_name": "Your Name",
       "password": "your-password-here"
     }
     ```
   - Click "Execute". You should get a 200 response with the new user.
   - This endpoint only works once. After the first user is created, it is disabled.
4. **Log in:**
   - Click the "Authorize" button (lock icon, top right of the Swagger page).
   - Enter the username and password you just created.
   - Leave `client_id` and `client_secret` empty.
   - Click "Authorize", then "Close".
   - All subsequent requests in Swagger will include your authentication token.

> **Note:** If the Authorize dialog causes a grey overlay issue, disable your
> browser's password manager for localhost, or use an incognito/private window.

### User Roles

| Role     | Permissions                                                      |
|----------|------------------------------------------------------------------|
| `admin`  | Full access. Can create and delete users, and do everything below. |
| `user`   | Can register images, create annotations, manage duplicates.       |
| `viewer` | Can browse images, view annotations, and view duplicates.         |

Only `admin` users can create new users via `POST /users/`.

### Stopping the containers

- Press `Ctrl+C` in the terminal where docker compose is running, or
- Run:
  ```
  docker compose down
  ```

### Resetting the database

To delete all data and start fresh:

```
docker compose down -v
```

The `-v` flag removes the persistent database volume.

### Inspecting the database with DBeaver

[DBeaver](https://dbeaver.io/download/) is a free database management tool for
browsing tables and running SQL queries.

1. Download and install from <https://dbeaver.io/download/>
2. Open DBeaver and click "New Database Connection" (plug icon).
3. Select "PostgreSQL" and click Next.
4. Enter the following connection settings:

   | Setting  | Value                |
   |----------|----------------------|
   | Host     | `localhost`          |
   | Port     | `5432`               |
   | Database | `imsor`              |
   | Username | `imsor`              |
   | Password | `imsor_dev_password` |

5. Click "Test Connection" to verify, then click "Finish".
6. Expand the connection in the left panel: `imsor > Schemas > public > Tables`
   to browse the database tables and their contents.

### Useful commands

| Command                          | Purpose                |
|----------------------------------|------------------------|
| `docker compose logs -f`         | View logs              |
| `docker compose up --build`      | Rebuild after changes  |
| `docker compose up --build -d`   | Run in background      |
