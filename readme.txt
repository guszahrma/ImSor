ImSor is short for image sorter.

the intenstion is for it to:
* search my local network for images I have distributed on different computers and servers,
* identify duplicates candidates
* allow presentation of duplicate candidates for hman made decision if either can be removed
* help me annotate images based on 
	* when they were taken
	* what is on the image
	* where images were taken
	* ...
* have the possibility to allow people in the images to veto or allow that they are shared with other users.
* have support for creating webpage slide shows based on annotation
* allow moving the imagefiles to better locations 
* annotation of images (identify who is in which image
	* manually by users
	* automated by AI like modules.


== Architecture ==

The system consists of four components, all Python-based.

--- 1. Central Web Service (Docker on Asustor NAS) ---
* Framework: Python + FastAPI
* Provides a REST API that all other components communicate with.
* Serves the Web Frontend.
* Manages user accounts, image metadata, annotations, duplicate tracking, and sharing permissions.

--- 2. Database (Docker on Asustor NAS) ---
* PostgreSQL running in a separate Docker container on the Asustor NAS.
* Stores all persistent data: image metadata, checksums, EXIF data, annotations,
  user accounts, face embeddings, duplicate pairs, sharing/veto decisions.

--- 3. Scanner Agent (Windows machines) ---
* Python script/service that runs on each Windows machine that has images to index.
* Scans configured folders for images.
* Calculates checksums for duplicate detection.
* Reads EXIF metadata (date taken, GPS coordinates, camera info, etc.).
* Reports discovered image metadata to the Central Web Service via its REST API.

--- 4. AI Service (Windows machine with sufficient hardware) ---
* Python service running on a machine with enough processing power for AI workloads.
* Uses local AI models for face detection, body detection, and face recognition.
* Pulls un-analyzed images from the Central Web Service, processes them, and pushes results back.
* Learns to recognize previously annotated persons over time using face embeddings.
* Can be dockerized if performance allows.

--- Data Flow ---
* Scanner Agent(s) discover images and report metadata to the Central Web Service.
* AI Service pulls unprocessed images from the Central Web Service, analyzes them, and returns results.
* Users interact through the Web Frontend to browse, annotate, review duplicates, manage sharing, and create slideshows.