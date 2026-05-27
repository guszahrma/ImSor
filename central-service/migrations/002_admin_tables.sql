-- 002_admin_tables.sql
-- Adds community-creation flag, camera assignments, person-user links, and community tables.

ALTER TABLE users ADD COLUMN IF NOT EXISTS can_create_community BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    make VARCHAR(200) NOT NULL,
    model VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_camera_user_make_model UNIQUE (user_id, make, model)
);

CREATE TABLE IF NOT EXISTS person_user_links (
    id SERIAL PRIMARY KEY,
    person_name VARCHAR(200) NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_person_name UNIQUE (person_name)
);

CREATE TABLE IF NOT EXISTS communities (
    id SERIAL PRIMARY KEY,
    creator_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_community_creator_name UNIQUE (creator_id, name)
);

CREATE TABLE IF NOT EXISTS community_members (
    id SERIAL PRIMARY KEY,
    community_id INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    CONSTRAINT uq_community_member UNIQUE (community_id, user_id)
);

CREATE TABLE IF NOT EXISTS community_granters (
    id SERIAL PRIMARY KEY,
    community_id INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    CONSTRAINT uq_community_granter UNIQUE (community_id, user_id)
);
