# ImSor — Domain Glossary

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
A record linking a User to a camera make and model they own, stored as (User, make, model). "Martin's Nikon COOLPIX S510" and "Martina's Nikon COOLPIX S510" are two distinct Camera records even if the physical devices are indistinguishable. When a make+model in an image's EXIF maps to exactly one User's Camera record, that User is the unambiguous Photographer. When it maps to multiple Camera records, Folder Attribution resolves which User's camera took the images. Serial number is a future refinement that would make (make, model, serial) sufficient to identify a specific physical device without needing Folder Attribution.

### Folder Attribution
A superuser-set record that resolves camera ownership ambiguity: "images in this folder path were taken by User X using Camera Y." Attributions inherit downward through subfolders unless overridden at a deeper level. Only needed when two users own cameras of the same make and model.

### Photographer
The User attributed as the owner of the camera that captured an image. Determined by Camera ownership, resolved by Folder Attribution when ambiguous. The Photographer is the primary authority over their images.

### Default Visibility
An image is visible only to its Photographer and Superusers by default. Access is closed unless explicitly extended.

### Community
A named group of Users, scoped to its creator. Uniqueness is per creator — (creator, name) is the key. "Adam's Family" and "Bob's Family" are distinct Communities that happen to share a name. Members may overlap freely.

### Community Creation Access
A permission flag that can be granted to any User by a Superuser, regardless of role. A User with this flag can create Communities, name them, add and remove members, and set which other Users are allowed to grant that Community access to images.

### Access Grant
A Photographer or Superuser extending visibility of images to a Community. Communities are identified by creator name and community name (e.g. "Adam's Family") to avoid ambiguity. The set of Users who may grant a given Community is controlled by the Community's creator.

### Veto
An annotated User's opt-out from having images containing them shared beyond the Photographer and Superuser. A Veto is image-level — one person vetoing an image removes it from all community-visible contexts for all users. The Photographer and Superuser can still view vetoed images in normal mode. Vetoed images are hidden for everyone without exception in Slideshow mode.

### Annotated User
A User who has been linked by a Superuser to a person name that appears in person_bbox annotations. Annotated Users may Veto images they appear in. The mechanism by which Annotated Users revoke broader access is to be detailed.

### Slideshow Mode
A presentation context in which vetoed images are hidden for all users without exception — including Superusers and Photographers. Privacy is absolute in this mode.

### Community Member Rights
A User who can see an image through Community membership may view and annotate it. They cannot extend access to others, revoke access, or delete anything.

---

## Long-term Architectural Direction

ImSor is intended to evolve toward a **federated peer-to-peer network**: each person runs their own instance, keeps their own images on their own infrastructure, and shares selectively with friends who run their own instances. No central authority. No platform owning your data.

This is not current scope, but it is a constraint: do not make decisions that would make federation impossible later.

Implications to keep in mind:
- User identity should remain globally addressable (email-based, not local integer IDs)
- Image references will eventually need to be globally addressable URLs, not only local file paths
- Communities may eventually span instances
- Access Grants need to be expressible in a form that can travel across instance boundaries
