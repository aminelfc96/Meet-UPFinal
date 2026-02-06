-- Authentication and Authorization Queries

-- Get user by ID (used by get_current_user)
-- Params: user_id
SELECT user_id, public_id, name FROM users WHERE user_id = ?;

-- Check if user is team admin
-- Params: team_id
SELECT admin_user_id FROM teams WHERE team_id = ?;

-- Check if user is meeting creator
-- Params: meeting_id
SELECT creator_user_id FROM meetings WHERE meeting_id = ?;

-- Check team membership status
-- Params: team_id, user_id
SELECT status FROM team_members WHERE team_id = ? AND user_id = ?;

-- Check meeting participation status
-- Params: meeting_id, user_id
SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?;