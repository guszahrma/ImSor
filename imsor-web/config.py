# ImSor Web configuration

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from credentials import (
    central_service_username as username,
    central_service_password as password,
    google_client_id,
    google_client_secret,
)

server_url = "http://localhost:8000"

# Local web server settings
host = "0.0.0.0"
port = 8080
server_name = "mzahr.asuscomm.com:7331"

# Maps stored path prefixes (forward-slash UNC) to local mount points.
# Add an entry here for each network share that holds images.
# Example: "//zahrdata/Home" -> "/mnt/zahrdata"
path_mappings = {
    "//zahrdata/Home": "/mnt/zahrdata",
}
