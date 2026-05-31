-- 004_person_table.sql
-- Introduces the Person entity with optional birthdate and user link.
-- Absorbs the former person_user_links table.

CREATE TABLE IF NOT EXISTS persons (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    birthdate DATE,
    user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_persons_name UNIQUE (name)
);

-- Migrate existing person_user_links rows
INSERT INTO persons (name, user_id, created_at)
SELECT person_name, user_id, created_at FROM person_user_links
ON CONFLICT (name) DO NOTHING;

-- Seed Selma Zahr
INSERT INTO persons (name, birthdate) VALUES ('Selma Zahr', '2007-11-08')
ON CONFLICT (name) DO UPDATE SET birthdate = EXCLUDED.birthdate;

DROP TABLE person_user_links;
