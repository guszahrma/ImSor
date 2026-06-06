# ImSor Web configuration

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from local_settings import (
    central_service_username as username,
    central_service_password as password,
    google_client_id,
    google_client_secret,
    active_bbox_model,
)

server_url = "http://localhost:8000"

# Local web server settings
host = "0.0.0.0"
port = 8080
server_name = "mzahr.asuscomm.com:7331"

# Maps stored path prefixes (forward-slash UNC) to local mount points.
# Add an entry here for each network share that holds images.
# Example: "//zahrdata/Home" -> "/mnt/zahrdata"

# Upload directory — where web-uploaded images are written locally, and the
# corresponding stored-path prefix recorded in the database.
upload_root = "/mnt/zahrdata_imsor/Uploads"
upload_stored_prefix = "//zahrdata/imsor/Uploads"

path_mappings = {
    "//zahrdata/Home": "/mnt/zahrdata_home/",
    "//zahrdata/imsor": "/mnt/zahrdata_imsor/",
}
