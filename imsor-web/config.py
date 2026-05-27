# ImSor Web configuration

from credentials import username, password

server_url = "http://localhost:8000"

# Local web server settings
host = "0.0.0.0"
port = 8080
server_name = "localhost:8080"

# Maps stored path prefixes (forward-slash UNC) to local mount points.
# Add an entry here for each network share that holds images.
# Example: "//zahrdata/Home" -> "/mnt/zahrdata"
path_mappings = {
    "//zahrdata/Home": "/mnt/zahrdata",
}
