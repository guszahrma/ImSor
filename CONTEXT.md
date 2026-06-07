# ImSor — Domain Glossary

## EXIF Orientation
The rotation embedded in an image file's EXIF metadata, indicating how the image should be displayed relative to how it was captured. Read by the scanner at scan time and stored as degrees (0, 90, 180, 270) in the `Image` table. Zero means no rotation needed. Images missing this tag are treated as 0°.

## Rotation Correction
A user-supplied adjustment stored as an Annotation (`annotation_type = "rotation_correction"`, value in degrees: 0, 90, 180, 270). Represents additional clockwise rotation to apply on top of the EXIF Orientation when displaying the image. One correction per image — upserted on change, deleted when cycled back to 0°. Any logged-in user may set it from the Rate page using the `R` key, which cycles 0° → 90° → 180° → 270° → 0°.

## Display Rotation
The final clockwise rotation applied when presenting an image: `(EXIF Orientation + Rotation Correction) % 360`. Computed at display time, never stored.

## Duplicate Pair
A persisted record that two specific images share the same checksum. Created by the scanner-agent when it finds two registered images with identical content. A Duplicate Pair is a detection artifact only — it carries no verdict and no resolved state.

## Duplicate Cluster
The set of all images that are transitively connected through Duplicate Pairs, derived dynamically at query time using union-find on the Duplicate Pair table. A Cluster is not stored — it is always computed. A Cluster grows automatically if the scanner later registers a new image whose checksum matches any existing member.

## Cluster Vote
A single annotator's full verdict on a Duplicate Cluster, submitted atomically. A Cluster Vote covers every image in the Cluster at the moment of submission. Submitting a new Cluster Vote replaces the same annotator's previous vote on the same Cluster.

## Duplicate Role
The verdict assigned to one image within a Cluster Vote. Stored as an Annotation with `annotation_type = "duplicate_role"` and `value = <image_id>`, where the image_id refers to the image the annotator designates as the keeper for this image:

- `value == this image's own id` — this annotator designates this image as the keeper (Original)
- `value == another image's id` — this annotator designates that other image as the keeper; this image is Redundant

One active Duplicate Role per annotator per image (upserted on revision).

## Original
An image whose Duplicate Role value equals its own image ID — this annotator votes to keep it. Original is always scoped to a single annotator's Cluster Vote. The same image may be Original in one annotator's vote and Redundant in another's — both are valid, uncontradicted verdicts. Whether an image is the Original across all annotators is determined by the Cleanup process, not stored.

## Redundant
An image whose Duplicate Role value equals another image's ID — this annotator votes to keep that other image and considers this one a copy. Redundant is always scoped to a single annotator's Cluster Vote.

## Annotation Queue
The ordered list of Duplicate Clusters presented to a logged-in annotator for review. Ordering:
1. Clusters with zero Duplicate Role annotations from any annotator — presented semi-randomly
2. Clusters the current annotator has not yet voted on — ordered by fewest distinct annotators first, then semi-randomly within ties
3. Clusters the current annotator has already voted on — excluded

## Cleanup
A separate, manually triggered process that reads all Duplicate Role annotations, identifies images with sufficient consensus as Redundant, and deletes the corresponding files. The threshold for "sufficient consensus" is determined at Cleanup time, not at annotation time.

---

## Access Model

### Camera
A record linking a User to a camera make and model they own, stored as (User, make, model). "Martin's Nikon COOLPIX S510" and "Martina's Nikon COOLPIX S510" are two distinct Camera records even if the physical devices are indistinguishable. When a Camera record is created, central-service retroactively assigns that User as Image Responsible on all Unattributed Images whose EXIF make and model match — but only if exactly one Camera record now exists for that (make, model) combination. Deleting a Camera record does not affect existing Image Responsible assignments. Serial number is a future refinement that would make (make, model, serial) sufficient to identify a specific physical device.

### Image Responsible
The User attributed as the owner of the camera that captured an image. Stored explicitly per image as `image_responsible_id` (nullable). For scanner-registered images, assigned at registration time when exactly one Camera record matches the image's EXIF make and model; left NULL when no Camera record matches or when multiple Camera records match. For images from an Upload Session, set unconditionally to the uploading user — Camera records do not apply. A Superuser may manually assign or reassign Image Responsible on any image via the Attribution Management page. The Image Responsible is the primary authority over their images.

### Unattributed Image
An image whose `image_responsible_id` is NULL — Image Responsible could not be determined automatically. Occurs when no Camera record matches the image's EXIF make and model, or when multiple Camera records match the same (make, model). Unattributed Images are surfaced to Superusers via the Attribution Management page for manual resolution.

### Attribution Management
A dedicated page accessible to Superusers listing all Unattributed Images. From this page a Superuser can manually assign an Image Responsible to individual images.

### Upload Session
A batch of images submitted together by a single user through the web upload interface, in a single form submission. All images in an Upload Session are attributed to the uploading user as Image Responsible unconditionally — Camera records and Folder Attribution do not apply. Each Upload Session is timestamped at the moment the submission begins. Only users with the `maintainer` or `superuser` role may initiate an Upload Session.

### Default Visibility
An image is visible only to its Image Responsible and Superusers by default. Access is closed unless explicitly extended.

### Community
A named group of Users, scoped to its creator. Uniqueness is per creator — (creator, name) is the key. "Adam's Family" and "Bob's Family" are distinct Communities that happen to share a name. Members may overlap freely.

### Community Creation Access
A permission flag that can be granted to any User by a Superuser, regardless of role. A User with this flag can create Communities, name them, add and remove members, and set which other Users are allowed to grant that Community access to images.

### Access Grant
An Image Responsible or Superuser extending visibility of images to a Community. Communities are identified by creator name and community name (e.g. "Adam's Family") to avoid ambiguity. The set of Users who may grant a given Community is controlled by the Community's creator.

### Veto
An annotated User's opt-out from having images containing them shared beyond the Image Responsible and Superuser. A Veto is image-level — one person vetoing an image removes it from all community-visible contexts for all users. The Image Responsible and Superuser can still view vetoed images in normal mode. Vetoed images are hidden for everyone without exception in Slideshow mode.

### Person
A named individual who appears in images. Stored as a first-class record with a name, an optional birthdate, and an optional link to a User account. Person absorbs the former PersonUserLink table — the user link is now a nullable field on Person rather than a separate join table. A Person with a linked User account is an Annotated User. A Person may have a birthdate without having a User account, and vice versa.

### Person Detection
An AI-produced bounding box asserting that a person appears at a specific location in an image. Stored as an Annotation with `annotation_type = "person_bbox"`, `source = "ai:<model>"`, no `user_id`, and a JSON value carrying spatial coordinates (`x`, `y`, `width`, `height`) and a confidence score. A Person Detection carries no identity — it records only that *a* person is present, not *who* that person is. Person Detections are never mutated after creation.

### Detection Adoption
A user's version of a Person Detection, created when the user connects a bbox to a Person. Stored as an Annotation with `annotation_type = "person_bbox"`, `source = "manual"`, the adopting user's `user_id`, and a JSON value containing `inherited_from: <original_annotation_id>` plus optional adjusted coordinates. If the user adjusts the bbox geometry, the same row is updated in place (upserted). One Detection Adoption per user per Person Detection. Implicitly confirms the detection location and establishes ownership.

### Supplemental Detection
A user-drawn bounding box for a person the AI did not detect. Stored as an Annotation with `annotation_type = "person_bbox"`, `source = "manual"`, the drawing user's `user_id`, and a JSON value with spatial coordinates but no `inherited_from` field. A Supplemental Detection is a first-class annotation, not a variant of Detection Adoption — it has no parent Person Detection.

### Person Identification
A single annotator's assertion, at a point in time, that the person inside a specific Detection Adoption or Supplemental Detection is a known Person (or is unidentifiable). Stored in a dedicated `person_identities` table referencing the Detection Adoption or Supplemental Detection and a nullable Person record. A null `person_id` means the annotator examined the bbox and could not identify the person. The table is append-only — each new assertion is a new row. The latest row per annotator per bbox annotation represents that annotator's current belief.

### Image File Event
A server-side record created each time the `/serve` endpoint attempts to serve an image file that cannot be found on disk. Stored in a dedicated `image_file_events` table. Each failed request produces one row containing the image ID and the timestamp the file was found missing (`detected_at`). When a subsequent `/serve` request for the same image succeeds, all unresolved rows for that image have their `resolved_at` timestamp set. Used to track which files are missing and for how long.

### Bbox Skip
A per-user assertion that no bounding box annotation work is needed on a specific image. Stored as an Annotation with `annotation_type = "bbox_skip"`, the user's `user_id`, and `value = "1"`. Images with a Bbox Skip from the requesting user are excluded from their Person Annotation Queue. Does not affect other users' queues or the image's annotations in any other way. Set from the Annotations page with the `N` key.

### Detection Dismissal
A user's assertion that a specific Person Detection is not relevant — they do not believe a person is present at that location. Stored in a dedicated `person_bbox_dismissals` table. Dismissal is per-user and does not affect other users' views. A Person Detection is permanently deleted only when it has been dismissed by at least 5 users and no Detection Adoption exists from any user.

### Person Annotation Queue
The ordered list of images presented to a logged-in annotator for person identification work. Images are assigned to one of five priority tiers based on how many bboxes on the image are linked to a Person, globally and by the current annotator. A bbox is a bbox regardless of origin (AI or user-drawn). Priority order:

1. No bboxes on the image are linked by anyone.
2. Some (but not all) bboxes are linked by someone; none by the current user.
3. All bboxes are linked by someone; none by the current user.
4. The current user has linked some but not all bboxes.
5. The current user has linked all bboxes — revisit in random order.

"Linked" means the annotator's latest Person Identification for that bbox has a non-null `person_id`. Display shows AI Person Detections by default, overridden by the user's own Detection Adoption where one exists.

### Annotated User
A User who has been linked by a Superuser to a Person record. Annotated Users may Veto images they appear in. The mechanism by which Annotated Users revoke broader access is to be detailed.

### Slideshow Mode
A presentation context in which vetoed images are hidden for all users without exception — including Superusers and the image's Image Responsible. Privacy is absolute in this mode.

### Community Member Rights
A User who can see an image through Community membership may view and annotate it. They cannot extend access to others, revoke access, or delete anything.

### Nomination
Martin marking an image with any slideshow_rating value, signalling that the image is a candidate for the party slideshow. Only Nominated images appear in the rating queues of other users (Selma, her mom). Nomination carries no quality threshold — a rating of 0 is still a Nomination.

### Skip
A personal annotation (`annotation_type = "skip"`) recording that a user has consciously passed over an image and does not want it to reappear in their rating queue. A Skip carries no quality verdict and does not affect other users' queues or the slideshow. Introduced in the deadend/selmas_student_party branch; all Skip annotations should be deleted when reverting to main.

### Unwelcomed
The default role assigned to any User who registers via Google OAuth. An Unwelcomed user can see only a holding page with a logout button — no ImSor content is accessible. A Superuser must manually promote the user to a higher role before they gain access. The holding page informs the user that the system owner has been notified and will assess their access.

### Bookmark
A personal annotation recording that a user wants to return to an image for a purpose not yet defined. One Bookmark per user per image — toggled on and off. A Bookmark has no value payload and no effect on any queue, rating, or sharing logic. Set from the Rate page with the `B` key.

---

## Long-term Architectural Direction

ImSor is intended to evolve toward a **federated peer-to-peer network**: each person runs their own instance, keeps their own images on their own infrastructure, and shares selectively with friends who run their own instances. No central authority. No platform owning your data.

This is not current scope, but it is a constraint: do not make decisions that would make federation impossible later.

Implications to keep in mind:
- User identity should remain globally addressable (email-based, not local integer IDs)
- Image references will eventually need to be globally addressable URLs, not only local file paths
- Communities may eventually span instances
- Access Grants need to be expressible in a form that can travel across instance boundaries
