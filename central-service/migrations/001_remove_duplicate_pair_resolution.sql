-- Migration 001: Remove verdict columns from duplicate_pairs
-- These columns are superseded by duplicate_role annotations on the Annotation table.
-- Run once against both dev and prod databases.

ALTER TABLE duplicate_pairs DROP COLUMN IF EXISTS resolved;
ALTER TABLE duplicate_pairs DROP COLUMN IF EXISTS resolution;
