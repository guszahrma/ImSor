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
