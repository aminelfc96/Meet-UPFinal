-- Meeting Management Queries

-- Get user's meetings
-- Params: user_id
SELECT m.meeting_id, m.title, m.creator_user_id, m.created_at,
       COUNT(mp.user_id) as participant_count
FROM meetings m
LEFT JOIN meeting_participants mp ON m.meeting_id = mp.meeting_id AND mp.status = 'approved'
WHERE m.meeting_id IN (
    SELECT meeting_id FROM meeting_participants 
    WHERE user_id = ? AND status = 'approved'
)
GROUP BY m.meeting_id, m.title, m.creator_user_id, m.created_at;

-- Create new meeting
-- Params: meeting_id, title, creator_user_id
INSERT INTO meetings (meeting_id, title, creator_user_id) VALUES (?, ?, ?);

-- Add meeting creator as participant
-- Params: meeting_id, creator_user_id
INSERT INTO meeting_participants (meeting_id, user_id, status) VALUES (?, ?, 'approved');

-- Check if meeting exists
-- Params: meeting_id
SELECT meeting_id, title, creator_user_id FROM meetings WHERE meeting_id = ?;

-- Check if user is meeting participant
-- Params: meeting_id, user_id
SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?;

-- Join meeting request
-- Params: meeting_id, user_id
INSERT INTO meeting_participants (meeting_id, user_id) VALUES (?, ?);

-- Get pending meeting requests
-- Params: meeting_id
SELECT mp.user_id, u.name, u.public_id, mp.joined_at
FROM meeting_participants mp
JOIN users u ON mp.user_id = u.user_id
WHERE mp.meeting_id = ? AND mp.status = 'pending'
ORDER BY mp.joined_at DESC;

-- Check if user is meeting creator
-- Params: meeting_id, user_id
SELECT title FROM meetings WHERE meeting_id = ? AND creator_user_id = ?;

-- Approve/reject meeting participant
-- Params: status, meeting_id, user_id
UPDATE meeting_participants SET status = ? WHERE meeting_id = ? AND user_id = ?;

-- Remove meeting participant
-- Params: meeting_id, user_id
DELETE FROM meeting_participants WHERE meeting_id = ? AND user_id = ?;

-- Block meeting participant
-- Params: meeting_id, user_id
UPDATE meeting_participants SET status = 'blocked' WHERE meeting_id = ? AND user_id = ?;

-- Get meeting participants
-- Params: meeting_id
SELECT mp.user_id, u.name, u.public_id, mp.status, mp.joined_at
FROM meeting_participants mp
JOIN users u ON mp.user_id = u.user_id
WHERE mp.meeting_id = ?
ORDER BY mp.joined_at;

-- Get approved meeting participants
-- Params: meeting_id
SELECT mp.user_id, u.name, u.public_id
FROM meeting_participants mp
JOIN users u ON mp.user_id = u.user_id
WHERE mp.meeting_id = ? AND mp.status = 'approved';

-- Delete meeting - cleanup participants
-- Params: meeting_id
DELETE FROM meeting_participants WHERE meeting_id = ?;

-- Delete meeting - delete meeting record
-- Params: meeting_id
DELETE FROM meetings WHERE meeting_id = ?;

-- Get meeting creator
-- Params: meeting_id
SELECT creator_user_id FROM meetings WHERE meeting_id = ?;