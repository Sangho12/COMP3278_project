CREATE TABLE IF NOT EXISTS comments (
  commentId INTEGER PRIMARY KEY AUTOINCREMENT,
  postId INTEGER NOT NULL,
  userId INTEGER NOT NULL,
  parent_comment_id INTEGER DEFAULT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (postId) REFERENCES posts (postId) ON DELETE CASCADE,
  FOREIGN KEY (userId) REFERENCES users (userId) ON DELETE CASCADE,
  FOREIGN KEY (parent_comment_id) REFERENCES comments (commentId) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS follows (
  followerId INTEGER NOT NULL,
  followingId INTEGER NOT NULL,
  PRIMARY KEY (followerId, followingId),
  FOREIGN KEY (followerId) REFERENCES users (userId),
  FOREIGN KEY (followingId) REFERENCES users (userId)
);

CREATE TABLE IF NOT EXISTS likes (
  userId INTEGER NOT NULL,
  postId INTEGER NOT NULL,
  PRIMARY KEY (userId, postId),
  FOREIGN KEY (userId) REFERENCES users (userId),
  FOREIGN KEY (postId) REFERENCES posts (postId)
);

CREATE TABLE IF NOT EXISTS notifications (
  notificationId INTEGER PRIMARY KEY AUTOINCREMENT,
  userId INTEGER NOT NULL,
  content TEXT NOT NULL,
  is_read INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (userId) REFERENCES users (userId)
);

CREATE TABLE IF NOT EXISTS posts (
  postId INTEGER PRIMARY KEY AUTOINCREMENT,
  userId INTEGER NOT NULL,
  content TEXT DEFAULT NULL,
  feeling_emoji TEXT DEFAULT NULL,
  image_url TEXT DEFAULT NULL,
  created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (userId) REFERENCES users (userId)
);

CREATE TABLE IF NOT EXISTS stories (
  storyId INTEGER PRIMARY KEY AUTOINCREMENT,
  userId INTEGER NOT NULL,
  image_video_url TEXT DEFAULT NULL,
  created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (userId) REFERENCES users (userId)
);

CREATE TABLE IF NOT EXISTS users (
  userId INTEGER PRIMARY KEY AUTOINCREMENT,
  profilePicture TEXT DEFAULT NULL,
  password TEXT NOT NULL,
  username TEXT NOT NULL UNIQUE
);

-- Analytics Views

-- Most liked posts
CREATE VIEW IF NOT EXISTS v_post_likes AS
    SELECT p.postId,
           p.content,
           u.username,
           COUNT(l.userId) AS like_count,
           p.created_at
    FROM   posts p
    JOIN   users u ON u.userId = p.userId
    LEFT JOIN likes l ON l.postId = p.postId
    GROUP  BY p.postId;

-- Most active users (by post count)
CREATE VIEW IF NOT EXISTS v_user_activity AS
    SELECT u.userId,
           u.username,
           COUNT(DISTINCT p.postId)   AS post_count,
           COUNT(DISTINCT l.userId)   AS likes_given,
           COUNT(DISTINCT c.commentId) AS comments_made
    FROM   users u
    LEFT JOIN posts    p ON p.userId = u.userId
    LEFT JOIN likes    l ON l.userId = u.userId
    LEFT JOIN comments c ON c.userId = u.userId
    GROUP  BY u.userId;