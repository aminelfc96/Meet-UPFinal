-- Team Management Queries

-- Get user's teams with member count
-- Params: user_id
SELECT 
    t.team_id, 
    t.name, 
    t.admin_user_id, 
    t.created_at,
    COUNT(tm.user_id) as member_count
FROM teams t
LEFT JOIN team_members tm ON t.team_id = tm.team_id AND tm.status = 'approved'
WHERE t.team_id IN (
    SELECT team_id FROM team_members 
    WHERE user_id = ? AND status = 'approved'
)
GROUP BY t.team_id, t.name, t.admin_user_id, t.created_at;

-- Create new team
-- Params: team_id, name, admin_user_id
INSERT INTO teams (team_id, name, admin_user_id) VALUES (?, ?, ?);

-- Add team creator as member
-- Params: team_id, admin_user_id
INSERT INTO team_members (team_id, user_id, status) VALUES (?, ?, 'approved');

-- Check if team exists and get admin
-- Params: team_id
SELECT name, admin_user_id FROM teams WHERE team_id = ?;

-- Check if user is already a member
-- Params: team_id, user_id
SELECT status FROM team_members WHERE team_id = ? AND user_id = ?;

-- Add user to team (join request)
-- Params: team_id, user_id
INSERT INTO team_members (team_id, user_id) VALUES (?, ?);

-- Get pending team requests (admin only)
-- Params: team_id
SELECT tm.user_id, u.name, u.public_id, tm.joined_at
FROM team_members tm
JOIN users u ON tm.user_id = u.user_id
WHERE tm.team_id = ? AND tm.status = 'pending'
ORDER BY tm.joined_at DESC;

-- Check if user is team admin
-- Params: team_id, user_id
SELECT name FROM teams WHERE team_id = ? AND admin_user_id = ?;

-- Approve/reject team member
-- Params: status, team_id, user_id
UPDATE team_members SET status = ? WHERE team_id = ? AND user_id = ?;

-- Remove team member
-- Params: team_id, user_id
DELETE FROM team_members WHERE team_id = ? AND user_id = ?;

-- Delete team - cleanup members
-- Params: team_id
DELETE FROM team_members WHERE team_id = ?;

-- Delete team - cleanup messages
-- Params: team_id
DELETE FROM team_messages WHERE team_id = ?;

-- Delete team - delete team record
-- Params: team_id
DELETE FROM teams WHERE team_id = ?;

-- Get team messages
-- Params: team_id
SELECT tm.message, tm.timestamp, u.name as user_name, u.public_id as user_public_id
FROM team_messages tm
JOIN users u ON tm.user_id = u.user_id
WHERE tm.team_id = ?
ORDER BY tm.timestamp DESC
LIMIT 50;

-- Send team message
-- Params: team_id, user_id, message
INSERT INTO team_messages (team_id, user_id, message) VALUES (?, ?, ?);

-- Check team membership for messages
-- Params: team_id, user_id
SELECT status FROM team_members WHERE team_id = ? AND user_id = ?;