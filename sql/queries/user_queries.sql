-- User Management Queries

-- Create new user
-- Params: user_id, public_id, name, password_hash
INSERT INTO users (user_id, public_id, name, password_hash) VALUES (?, ?, ?, ?);

-- Get user by ID (for authentication)
-- Params: user_id
SELECT user_id, public_id, name, password_hash FROM users WHERE user_id = ?;

-- Get user profile (no password)
-- Params: user_id  
SELECT user_id, public_id, name, created_at FROM users WHERE user_id = ?;

-- Get user basic info (for display)
-- Params: user_id
SELECT user_id, public_id, name FROM users WHERE user_id = ?;

-- Delete user - cleanup team messages
-- Params: user_id
DELETE FROM team_messages WHERE user_id = ?;

-- Delete user - cleanup team memberships
-- Params: user_id
DELETE FROM team_members WHERE user_id = ?;

-- Delete user - cleanup meeting participations
-- Params: user_id
DELETE FROM meeting_participants WHERE user_id = ?;

-- Delete user - get admin teams for cleanup
-- Params: user_id
SELECT team_id FROM teams WHERE admin_user_id = ?;

-- Delete user - get creator meetings for cleanup
-- Params: user_id
SELECT meeting_id FROM meetings WHERE creator_user_id = ?;

-- Delete user - cleanup team members (for admin teams)
-- Params: team_id
DELETE FROM team_members WHERE team_id = ?;

-- Delete user - cleanup team messages (for admin teams)
-- Params: team_id
DELETE FROM team_messages WHERE team_id = ?;

-- Delete user - cleanup teams (for admin teams)
-- Params: team_id
DELETE FROM teams WHERE team_id = ?;

-- Delete user - cleanup meeting participants (for creator meetings)
-- Params: meeting_id
DELETE FROM meeting_participants WHERE meeting_id = ?;

-- Delete user - cleanup meetings (for creator meetings)
-- Params: meeting_id
DELETE FROM meetings WHERE meeting_id = ?;

-- Delete user - final user deletion
-- Params: user_id
DELETE FROM users WHERE user_id = ?;