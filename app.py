import hashlib
import sqlite3
import os
from datetime import datetime
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for, session, jsonify, flash)

DATABASE = 'HkuGram.db'
SECRET_KEY = 'hkugram_comp3278'

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Database
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
    db.commit()
    # no-op: keep schema from HkuGram.sql; stories are stored with image_video_url and created_at

#  Auth helpers 
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

# root
@app.route('/')
def index():
  if 'userId' in session:
    return redirect(url_for('feed'))
  return redirect(url_for('login'))

# user authentication - login
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
      

# user authentication - register

@app.route('/register', methods=['GET', 'POST'])
def register():
  if request.method == 'POST':
    username = request.form.get('username')
    password = request.form.get('password')
    profile_pic = request.form.get('profile_picture') or 'https://example.com/default-avatar.png'
    if not username or not password:
      flash("Incorrect username or password.")
      return redirect(url_for('register'))
      
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    db = get_db()
    
    try:
      db.execute(
        "INSERT INTO users (username, password, profilePicture) VALUES (?, ?, ?)", 
        (username, hashed_password, profile_pic)
      )
      db.commit()
      flash("Registration successful! Please go to log in.")
      return redirect(url_for('login'))
      
    except sqlite3.IntegrityError:
      flash("Username already exists! Try another one.")
  return render_template('register.html')
  
# user authentication - logout
@app.route('/logout')
def logout():

  session.pop('userId', None)
  session.pop('username', None)
  flash("You have been logged out.")
  return redirect(url_for('login'))

# Edit Profile Route

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
  db = get_db()
  if request.method == 'POST':
    new_pic = request.form.get('profile_picture')
    db.execute("UPDATE users SET profilePicture = ? WHERE userId = ?", (new_pic, session['userId']))
    db.commit()
    flash("Profile updated!")
    return redirect(url_for('profile', username=session['username']))
  user = db.execute("SELECT * FROM users WHERE userId = ?", (session['userId'],)).fetchone()
  return render_template('edit_profile.html', user=user)


# Feed
@app.route('/feed') # feed.html
@login_required
def feed():
  sort = request.args.get('sort', 'new') # depend on UI
  db   = get_db()
  order = "p.created_at DESC" if sort == 'new' else "like_count DESC"
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
    """, (session['userId'], session['userId'])).fetchall()
  # fetch users who have active stories in the last 24 hours
  story_users = db.execute("""
    SELECT u.userId, u.username, u.profilePicture, COUNT(s.storyId) AS story_count
    FROM stories s
    JOIN users u ON u.userId = s.userId
    WHERE datetime(s.created_at) >= datetime('now', '-1 day')
    GROUP BY u.userId
    ORDER BY MAX(s.created_at) DESC
  """).fetchall()

  return render_template('feed.html', posts=posts, sort=sort, user=current_user(), story_users=story_users)
  
# Posts
@app.route('/post/new', methods=['GET','POST']) # new_post.html
@login_required 
def new_post():
  if request.method == 'POST':
    content = request.form['content'].strip() or None
    image_url = request.form.get('image_url', '').strip() or None
    feeling_emoji = request.form.get('feeling_emoji', '').strip() or None
    if content is None and image_url is None: # similar to facebook (can be thoughts, pic, or both in a post)
      flash('Share your thoughts!', 'error')
      return render_template('new_post.html', user=current_user())
    db = get_db()
    db.execute("INSERT INTO posts (userId, content, image_url, feeling_emoji) VALUES (?,?,?,?)", (session['userId'], content, image_url, feeling_emoji)) 
    db.commit()
    flash('Post published!', 'success')
    return redirect(url_for('feed'))
  return render_template('new_post.html', user=current_user())


# Stories
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


@app.route('/stories/<username>')
@login_required
def stories(username):
  db = get_db()
  prof = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
  if not prof:
    flash('User not found.', 'error')
    return redirect(url_for('feed'))
  stories_rows = db.execute("SELECT s.*, u.username, u.profilePicture FROM stories s JOIN users u ON u.userId = s.userId WHERE s.userId = ? AND datetime(s.created_at) >= datetime('now','-1 day') ORDER BY s.created_at ASC", (prof['userId'],)).fetchall()
  stories = [dict(r) for r in stories_rows]
  if not stories:
    flash('No active stories for this user.', 'error')
    return redirect(url_for('profile', username=username))
  return render_template('stories.html', prof=prof, stories=stories, user=current_user())

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

@app.route('/post/<int:postId>') # post.html
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

@app.route('/post/<int:postId>/delete', methods=['POST'])
@login_required
def delete_post(postId):
  db = get_db()
  post = db.execute("SELECT userId FROM posts WHERE postId=?",(postId,)).fetchone()
  if post and post['userId'] == session['userId']:
    db.execute("DELETE FROM posts WHERE postId=?", (postId,))
    db.commit()
    flash('Post deleted.', 'success')
  else:
    flash('Unauthorized action.', 'error')
  return redirect(url_for('feed'))

# Likes
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

# Comments 
@app.route('/post/<int:postId>/comment', methods=['POST']) #post.html
@login_required
def add_comment(postId):
  content = request.form.get('content', '').strip()
  parentComment = request.form.get('parentComment')
  if content:
    db = get_db()
    db.execute("INSERT INTO comments (postId, userId, content, parent_comment_id) VALUES (?,?,?,?)",
               (postId, session['userId'], content, parentComment)) # HTML send back the button clicked with its parentid
    db.commit()
  return redirect(url_for('view_post', postId=postId))

# Profile
@app.route('/profile/<username>') # profile.html
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

  print(posts)
  stats = db.execute("SELECT * FROM v_user_activity WHERE userId=?",(prof['userId'],)).fetchone()

  # follower / following counts and whether the current user follows this profile
  follower_count = db.execute("SELECT COUNT(*) FROM follows WHERE followingId=?", (prof['userId'],)).fetchone()[0]
  following_count = db.execute("SELECT COUNT(*) FROM follows WHERE followerId=?", (prof['userId'],)).fetchone()[0]
  is_following = False
  cu = current_user()
  if cu:
    is_following = db.execute("SELECT 1 FROM follows WHERE followerId=? AND followingId=?", (cu['userId'], prof['userId'])).fetchone() is not None

  return render_template('profile.html', prof=prof, posts=posts, stats=stats, user=current_user(), follower_count=follower_count, following_count=following_count, is_following=is_following)

# Analytics
@app.route('/analytics') # analytics.html
@login_required
def analytics():
  db = get_db()
  top_posts = db.execute("SELECT * FROM v_post_likes ORDER BY like_count DESC LIMIT 10").fetchall()
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
  # toggle follow
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
  
if __name__ == '__main__':
  if not os.path.exists(DATABASE):
    init_db()
  else:
    # still apply any new schema changes
    with app.app_context():
      db = get_db()
      with open('HkuGram.sql') as f:
        db.executescript(f.read())
      db.commit()
  app.run(debug=True, port=5000, threaded=True)




