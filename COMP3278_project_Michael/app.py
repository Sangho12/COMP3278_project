import hashlib
import sqlite3
import os
from datetime import datetime
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for, session, jsonify, flash)

# App Configuration
DATABASE = 'HkuGram.db'
SECRET_KEY = 'hkugram_comp3278'
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Database Helpers
def get_db() -> sqlite3.Connection:
  db = getattr(g, '_database', None)
  if db is None:
    db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
  return db

@app.teardown_appcontext
def close_db(_):
  db = getattr(g, '_database', None)
  if db is not None:
    db.close()

def init_db():
  with app.app_context():
    db = get_db()
    with open('HkuGram.sql', 'r') as f:
      db.executescript(f.read())
    # Create notification read tracking table
    db.execute("""
      CREATE TABLE IF NOT EXISTS notification_read (
          userId INTEGER,
          postId INTEGER,
          PRIMARY KEY (userId, postId),
          FOREIGN KEY (userId) REFERENCES users(userId) ON DELETE CASCADE,
          FOREIGN KEY (postId) REFERENCES posts(postId) ON DELETE CASCADE
      )
    """)
    db.commit()

# Auth Helpers
def login_required(f): 
  @wraps(f)
  def decorated(*args, **kwargs):
    if 'userId' not in session:
      return redirect(url_for('login'))
    return f(*args, **kwargs)
  return decorated

def current_user():
  if 'userId' not in session:
    return None
  db = get_db()
  return db.execute("SELECT * FROM users WHERE userId=?", (session['userId'],)).fetchone()

# Root Route
@app.route('/')
def index():
  if 'userId' in session:
    return redirect(url_for('feed'))
  return redirect(url_for('login'))

# User Authentication - Login
@app.route('/login', methods=['GET', 'POST'])
def login():
  if request.method == 'POST':
    username = request.form.get('username')
    password = request.form.get('password')
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, hashed_password)).fetchone()
    if user:
      session['userId'] = user['userId']
      session['username'] = user['username']
      return redirect(url_for('feed'))
      
    else:
      flash("Invalid username or password.")
  return render_template('login.html')
      
# User Authentication - Register
@app.route('/register', methods=['GET', 'POST'])
def register():
  if request.method == 'POST':
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
      flash("Incorrect username or password.")
      return redirect(url_for('register'))
      
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    db = get_db()
    
    try:
      db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
      db.commit()
      flash("Registration successful! Please go to log in.")
      return redirect(url_for('login'))
      
    except sqlite3.IntegrityError:
      flash("Username already exists! Try another one.")
  return render_template('register.html')

# User Authentication - Logout
@app.route('/logout')
def logout():
  session.pop('userId', None)
  session.pop('username', None)
  flash("You have been logged out.")
  return redirect(url_for('login'))

# Feed Route (FIXED: No Early Return)
@app.route('/feed') 
@login_required
def feed():
  sort = request.args.get('sort', 'new') 
  db   = get_db()
  current_user_id = session['userId']
  order = "p.created_at DESC" if sort == 'new' else "like_count DESC"

  # Notification Logic
  following = db.execute("SELECT followingId FROM follows WHERE followerId = ?", (current_user_id,)).fetchall()
  following_ids = [f['followingId'] for f in following] if following else []
  
  new_post_notifications = []
  if following_ids:
    placeholders = ', '.join('?' * len(following_ids))
    new_post_notifications = db.execute(f"""
      SELECT u.username, p.postId, p.created_at
      FROM posts p
      JOIN users u ON u.userId = p.userId
      LEFT JOIN notification_read nr ON nr.postId = p.postId AND nr.userId = ?
      WHERE p.userId IN ({placeholders})
        AND datetime(p.created_at) >= datetime('now', '-1 day')
        AND nr.postId IS NULL
      ORDER BY p.created_at DESC
    """, [current_user_id] + following_ids).fetchall()

  # Posts Query (MOVED BEFORE RETURN)
  posts = db.execute(f"""SELECT p.*, u.username, u.userId, u.profilePicture,
    COUNT(DISTINCT l.userId) AS like_count, 
    COUNT(DISTINCT c.commentId) AS comment_count,
    MAX(CASE WHEN l2.userId = ? THEN 1 ELSE 0 END) AS user_liked
    FROM posts p
    JOIN users u ON u.userId = p.userId
    LEFT JOIN likes l ON l.postId = p.postId
    LEFT JOIN comments c ON c.postId = p.postId
    LEFT JOIN likes    l2 ON l2.postId = p.postId AND l2.userId = ?
    GROUP  BY p.postId
    ORDER  BY {order}
    """, (current_user_id, current_user_id)).fetchall()
  
  # Stories Query (MOVED BEFORE RETURN)
  story_users = db.execute("""
    SELECT u.userId, u.username, u.profilePicture
    FROM (
      SELECT userId, MAX(created_at) AS latest_story
      FROM stories
      WHERE datetime(created_at) >= datetime('now', '-1 day')
      GROUP BY userId
    ) AS latest
    JOIN users u ON u.userId = latest.userId
    LEFT JOIN follows f ON f.followingId = u.userId AND f.followerId = ?
    WHERE f.followerId IS NOT NULL OR u.userId = ?
    ORDER BY latest.latest_story DESC
  """, (current_user_id, current_user_id)).fetchall()
  
  # Single Return (FIXED: All variables defined first)
  return render_template('feed.html', 
    posts=posts, 
    sort=sort, 
    user=current_user(), 
    story_users=story_users,
    new_post_notifications=new_post_notifications)
  
# New Post Route (FIXED COLUMN ORDER)
@app.route('/post/new', methods=['GET','POST'])
@login_required 
def new_post():
  if request.method == 'POST':
    content = request.form['content'].strip() or None
    image_url = request.form.get('image_url', '').strip() or None
    feeling_emoji = request.form.get('feeling_emoji', '').strip() or None
    
    if content is None and image_url is None:
      flash('Share your thoughts!', 'error')
      return render_template('new_post.html', user=current_user())
    
    db = get_db()
    # 👇 FIXED: Column order matches your SQL table
    db.execute("INSERT INTO posts (userId, content, feeling_emoji, image_url) VALUES (?,?,?,?)", (session['userId'], content, feeling_emoji, image_url)) 
    db.commit()
    flash('Post published!', 'success')
    return redirect(url_for('feed'))
  return render_template('new_post.html', user=current_user())

# Mark Notification as Read Route
@app.route('/notification/read/<int:postId>')
@login_required
def mark_notification_read(postId):
  db = get_db()
  user_id = session['userId']
  
  try:
    db.execute(
      "INSERT INTO notification_read (userId, postId) VALUES (?, ?)",
      (user_id, postId)
    )
    db.commit()
  except sqlite3.IntegrityError:
    pass
  return redirect(url_for('view_post', postId=postId))

# New Story Route
@app.route('/story/new', methods=['GET', 'POST'])
@login_required
def new_story():
  db = get_db()
  if request.method == 'POST':
    image_url = request.form.get('image_url', '').strip() or None
    if not image_url:
      flash('Please provide an image or video URL for the story.', 'error')
      return render_template('new_story.html', user=current_user())
    db.execute("INSERT INTO stories (userId, image_video_url) VALUES (?,?)", (session['userId'], image_url))
    db.commit()
    flash('Story posted!', 'success')
    return redirect(url_for('feed'))
  return render_template('new_story.html', user=current_user())

# View Stories Route
@app.route('/stories/<username>')
@login_required
def stories(username):
  db = get_db()
  prof = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
  if not prof:
    flash('User not found.', 'error')
    return redirect(url_for('feed'))
  stories_rows = db.execute("""
    SELECT s.*, u.username, u.profilePicture
    FROM stories s
    JOIN users u ON u.userId = s.userId
    WHERE s.userId = ?
    AND datetime(s.created_at) >= datetime('now', '-1 day')
    ORDER BY s.created_at DESC
    LIMIT 1
  """, (prof['userId'],)).fetchall()
  stories = [dict(r) for r in stories_rows]
  if not stories:
    flash('No active stories for this user.', 'error')
    return redirect(url_for('profile', username=username))
  return render_template('stories.html', prof=prof, stories=stories, user=current_user())

# Comment Tree Helper
def build_comment_tree(comments):
    by_id = {}
    for c in comments:
        by_id[c['commentId']] = {**c, 'children': []}
    roots = []
    for c in comments:
        node = by_id[c['commentId']]
        parent_id = c.get('parent_comment_id')
        if parent_id in (None, 0):
            roots.append(node)
        else:
            parent = by_id.get(parent_id)
            if parent:
                parent['children'].append(node)
            else:
                roots.append(node)
    return roots

# View Single Post Route
@app.route('/post/<int:postId>') 
@login_required
def view_post(postId):
  db = get_db()
  post = db.execute("""SELECT p.*, u.username, u.profilePicture,
    COUNT(DISTINCT l.userId) AS like_count,
    MAX(CASE WHEN l2.userId=? THEN 1 ELSE 0 END) AS user_liked
    FROM   posts p
    JOIN   users u ON u.userId = p.userId
    LEFT JOIN likes l  ON l.postId  = p.postId
    LEFT JOIN likes l2 ON l2.postId = p.postId AND l2.userId = ?
    WHERE  p.postId = ?
    GROUP  BY p.postId
    """, (session['userId'], session['userId'], postId)).fetchone()
  if not post:
    flash('Post not found.', 'error')
    return redirect(url_for('feed'))
  comments = db.execute("""
    SELECT c.*, u.username, u.profilePicture
    FROM   comments c
    JOIN   users u ON u.userId = c.userId
    WHERE  c.postId = ?
    ORDER  BY c.created_at ASC
    """, (postId,)).fetchall()
  
  comment_tree = build_comment_tree([dict(row) for row in comments])
  return render_template('post.html', post=post, comments = comment_tree, user=current_user())

# Delete Post Route
@app.route('/post/<int:postId>/delete', methods=['POST'])
@login_required
def delete_post(postId):
  db = get_db()
  post = db.execute("SELECT userId FROM posts WHERE postId=?",(postId,)).fetchone()
  if post and post['userId'] == session['userId']:
    db.execute("DELETE FROM likes WHERE postId=?", (postId,))
    db.execute("DELETE FROM comments WHERE postId=?", (postId,))
    db.execute("DELETE FROM posts WHERE postId=?", (postId,))
    db.commit()
    flash('Post deleted.', 'success')
  else:
    flash('Unauthorized action.', 'error')
  return redirect(url_for('feed'))

# Toggle Like Route
@app.route('/post/<int:postId>/like', methods=['POST'])
@login_required
def toggle_like(postId):
  db  = get_db()
  userId = session['userId']
  existing = db.execute(
    "SELECT * FROM likes WHERE postId=? AND userId=?",(postId, userId)
  ).fetchone()
  if existing:
    db.execute("DELETE FROM likes WHERE postId=? AND userId=?",(postId, userId))
    liked = False
  else:
    db.execute("INSERT INTO likes (postId, userId) VALUES (?,?)", (postId, userId))
    liked = True
  db.commit()
  count = db.execute(
    "SELECT COUNT(*) FROM likes WHERE postId=?", (postId,)
  ).fetchone()[0]
  return jsonify({'liked': liked, 'count': count})

# Add Comment Route
@app.route('/post/<int:postId>/comment', methods=['POST'])
@login_required
def add_comment(postId):
  content = request.form.get('content', '').strip()
  parentComment = request.form.get('parentComment')
  if content:
    db = get_db()
    db.execute("INSERT INTO comments (postId, userId, content, parent_comment_id) VALUES (?,?,?,?)",
               (postId, session['userId'], content, parentComment))
    db.commit()
  return redirect(url_for('view_post', postId=postId))

# User Profile Route (FIXED: Added @login_required)
@app.route('/profile/<username>') 
@login_required
def profile(username):
  db   = get_db()
  prof = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
  if not prof:
    flash('User not found.', 'error')
    return redirect(url_for('feed'))
  posts = db.execute("""
    SELECT p.*, COUNT(DISTINCT l.userId) AS like_count,
    COUNT(DISTINCT c.commentId) AS comment_count
    FROM   posts p
    LEFT JOIN likes l ON l.postId = p.postId
    LEFT JOIN comments c ON c.postId = p.postId
    WHERE  p.userId = ?
    GROUP  BY p.postId
    ORDER  BY p.created_at DESC
  """, (prof['userId'],)).fetchall()
  stats = db.execute("SELECT * FROM v_user_activity WHERE userId=?",(prof['userId'],)).fetchone()
  follower_count = db.execute("SELECT COUNT(*) FROM follows WHERE followingId=?", (prof['userId'],)).fetchone()[0]
  following_count = db.execute("SELECT COUNT(*) FROM follows WHERE followerId=?", (prof['userId'],)).fetchone()[0]
  is_following = False
  cu = current_user()
  if cu:
    is_following = db.execute("SELECT 1 FROM follows WHERE followerId=? AND followingId=?", (cu['userId'], prof['userId'])).fetchone() is not None
  return render_template('profile.html', prof=prof, posts=posts, stats=stats, user=current_user(), follower_count=follower_count, following_count=following_count, is_following=is_following)

# Edit Profile Route
@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    db = get_db()
    user_id = session['userId']
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_profile_pic = request.form.get('profile_picture')
        new_password = request.form.get('password')
        try:
            db.execute("""
                UPDATE users 
                SET username = ?, profilePicture = ?
                WHERE userId = ?
            """, (new_username, new_profile_pic, user_id))
            
            if new_password and new_password.strip():
                hashed_pw = hashlib.sha256(new_password.encode()).hexdigest()
                db.execute("UPDATE users SET password = ? WHERE userId = ?", (hashed_pw, user_id))
            
            db.commit()
            session['username'] = new_username
            flash("Profile updated successfully!", "success")
            return redirect(url_for('profile', username=new_username))
        except sqlite3.IntegrityError:
            flash("Username already taken.", "error")
            return redirect(url_for('edit_profile'))
    user = db.execute("SELECT * FROM users WHERE userId = ?", (user_id,)).fetchone()
    
    posts = db.execute("""
        SELECT p.*, COUNT(DISTINCT l.userId) AS like_count,
        COUNT(DISTINCT c.commentId) AS comment_count
        FROM   posts p
        LEFT JOIN likes l ON l.postId = p.postId
        LEFT JOIN comments c ON c.postId = p.postId
        WHERE  p.userId = ?
        GROUP  BY p.postId
        ORDER  BY p.created_at DESC
    """, (user_id,)).fetchall()
    
    return render_template('edit_profile.html', user=user, posts=posts)

# Analytics Route
@app.route('/analytics')
@login_required
def analytics():
  db = get_db()
  top_posts = db.execute("""
    SELECT 
      p.postId, 
      p.content, 
      p.image_url, 
      u.username,
      COUNT(DISTINCT l.userId) AS like_count,
      COUNT(DISTINCT c.commentId) AS comment_count
    FROM posts p
    JOIN users u ON u.userId = p.userId
    LEFT JOIN likes l ON l.postId = p.postId
    LEFT JOIN comments c ON c.postId = p.postId
    GROUP BY p.postId
    ORDER BY like_count DESC
    LIMIT 10
  """).fetchall()
  top_users = db.execute("""
        SELECT a.*, u.profilePicture 
        FROM v_user_activity a
        JOIN users u ON a.userId = u.userId
        ORDER BY post_count DESC LIMIT 10
    """).fetchall()
  total_posts = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
  total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
  total_likes = db.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
  return render_template('analytics.html',top_posts=top_posts, top_users=top_users, total_posts=total_posts, 
                         total_users=total_users, total_likes=total_likes, user=current_user())

# Follow/Unfollow Route
@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
  db = get_db()
  target = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
  if not target:
    flash('User not found.', 'error')
    return redirect(url_for('feed'))
  if target['userId'] == session['userId']:
    flash('You cannot follow yourself.', 'error')
    return redirect(url_for('profile', username=username))
  existing = db.execute("SELECT * FROM follows WHERE followerId=? AND followingId=?", (session['userId'], target['userId'])).fetchone()
  if existing:
    db.execute("DELETE FROM follows WHERE followerId=? AND followingId=?", (session['userId'], target['userId']))
    db.commit()
    flash(f'Unfollowed {username}.', 'success')
  else:
    db.execute("INSERT INTO follows (followerId, followingId) VALUES (?,?)", (session['userId'], target['userId']))
    db.commit()
    flash(f'Now following {username}.', 'success')
  return redirect(url_for('profile', username=username))

# Search Route
@app.route('/search')
@login_required
def search():
  q = request.args.get('q','').strip()
  db = get_db()
  results = []
  if q:
    like = f"%{q}%"
    results = db.execute("SELECT userId, username, profilePicture FROM users WHERE username LIKE ? LIMIT 50", (like,)).fetchall()
  return render_template('search.html', q=q, results=results, user=current_user())

# Followers List Route
@app.route('/followers/<username>')
@login_required
def followers(username):
  db = get_db()
  prof = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
  if not prof:
    flash('User not found.', 'error')
    return redirect(url_for('feed'))
  rows = db.execute("SELECT u.userId, u.username, u.profilePicture FROM follows f JOIN users u ON f.followerId = u.userId WHERE f.followingId = ?", (prof['userId'],)).fetchall()
  return render_template('followers.html', prof=prof, users=rows, user=current_user(), title='Followers')

# Following List Route
@app.route('/following/<username>')
@login_required
def following(username):
  db = get_db()
  prof = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
  if not prof:
    flash('User not found.', 'error')
    return redirect(url_for('feed'))
  rows = db.execute("SELECT u.userId, u.username, u.profilePicture FROM follows f JOIN users u ON f.followingId = u.userId WHERE f.followerId = ?", (prof['userId'],)).fetchall()
  return render_template('followers.html', prof=prof, users=rows, user=current_user(), title='Following')

# Combined Follows Page
@app.route('/follows/<username>')
@login_required
def follows(username):
  db = get_db()
  prof = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
  if not prof:
    flash('User not found.', 'error')
    return redirect(url_for('feed'))
  
  follower_users = db.execute("SELECT u.userId, u.username, u.profilePicture FROM follows f JOIN users u ON f.followerId = u.userId WHERE f.followingId = ?", (prof['userId'],)).fetchall()
  following_users = db.execute("SELECT u.userId, u.username, u.profilePicture FROM follows f JOIN users u ON f.followingId = u.userId WHERE f.followerId = ?", (prof['userId'],)).fetchall()
  
  return render_template('followers.html', prof=prof, follower_users=follower_users, following_users=following_users, user=current_user())

# App Startup (ONLY ONE BLOCK, AT THE BOTTOM)
if __name__ == '__main__':
  if not os.path.exists(DATABASE):
    init_db()
  else:
    with app.app_context():
      db = get_db()
      with open('HkuGram.sql') as f:
        db.executescript(f.read())
      db.commit()
  app.run(debug=True, port=5000, threaded=True)