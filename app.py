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
    with open('schema.sql', 'r') as f:
      db.executescript(f.read())
    db.commit()

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
  return db.execute("SELECT * FROM User WHERE userId=?", (session['userId'],)).fetchone()

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
    user = db.execute("SELECT * FROM User WHERE username = ? AND password = ?", (username, hashed_password)).fetchone()
    
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
    
    if not username or not password:
      flash("Incorrect username or password.")
      return redirect(url_for('register'))
      
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    db = get_db()
    
    try:
      db.execute("INSERT INTO User (username, password) VALUES (?, ?)", (username, hashed_password))
      db.commit()
      flash("Registration successful! Please go to log in.")
      return redirect(url_for('login'))
      
    except sqlite3.IntegrityError:
      flash("Username already exists! Try another one.")
  return render_template('register.html')
  
# user authentication - logout
@app.route('/logout')
def logout():
  session.pop('username', None)
  flash("You have been logged out.")
  return redirect(url_for('login'))

# Feed
@app.route('/feed')
@login_required
def feed():
  sort = request.args.get('sort', 'new') # depend on UI
  db   = get_db()
  order = "p.created_at DESC" if sort == 'new' else "like_count DESC"

  posts = db.execute(f"""
    SELECT p.postId, p.content, p.image_url, p.created_at, u.username, u.userId,
      COUNT(DISTINCT l.like_id) AS like_count, 
      COUNT(DISTINCT c.comment_id) AS comment_count,
      MAX(CASE WHEN l2.userId = ? THEN 1 ELSE 0 END) AS user_liked
    FROM   Post p
    JOIN   users u  ON u.userId  = p.userId
    LEFT JOIN likes    l  ON l.postId  = p.postId
    LEFT JOIN comments c  ON c.postId  = p.postId
    LEFT JOIN likes    l2 ON l2.postId = p.postId AND l2.userId = ?
    GROUP  BY p.postId
    ORDER  BY {order}
    """, (session['userId'], session['userId'])).fetchall()
  
  # add notification here check noti database if there is unread 
  # --> return a boolean for ui to use a red dot indicate?
  return render_template('feed.html', posts=posts, sort=sort, user=current_user())
  
# Posts
@app.route('/post/new', methods=['GET','POST'])
@login_required 
def new_post():
  if request.method == 'POST':
    content = request.form['content'].strip() or None
    image_url = request.form.get('image_url', '').strip() or None
    if content is None and image_url is None: # similar to facebook (can be thoughts, pic, or both in a post)
      flash('Share your thoughts!', 'error')
      return render_template('new_post.html', user=current_user()) #the new post html DEPEND on URL
    db = get_db()
    db.execute("INSERT INTO Post (username, content, image_url) VALUES (?,?,?)", (session['username'], content, image_url)) 
    db.commit()
    flash('Post published!', 'success')
    return redirect(url_for('feed'))# to feed url
  return render_template('new_post.html', user=current_user()) #the new post html DEPEND ON UI


@app.route('/post/<int:post_id>')
@login_required
def view_post(post_id):
  db = get_db()
  post = db.execute("""
    SELECT p.*, u.username,
    COUNT(DISTINCT l.like_id) AS like_count,
    MAX(CASE WHEN l2.username=? THEN 1 ELSE 0 END) AS user_liked
    FROM   posts p
    JOIN   users u ON u.username = p.username
    LEFT JOIN likes l  ON l.post_id  = p.post_id
    LEFT JOIN likes l2 ON l2.post_id = p.post_id AND l2.username = ?
    WHERE  p.post_id = ?
    GROUP  BY p.post_id
    """, (session['username'], session['username'], post_id)).fetchone()
  if not post:
    flash('Post not found.', 'error')
    return redirect(url_for('feed'))

  Parentcomments = db.execute("""
    SELECT c.*, u.username
    FROM   comments c
    JOIN   users u ON u.username = c.username
    WHERE  c.post_id = ? AND c.parentComment IS NULL
    ORDER  BY c.created_at ASC
    """, (post_id,)).fetchall()
  
  Childcomments = db.execute("""
    SELECT c.*, u.username
    FROM   comments c
    JOIN   users u ON u.username = c.username
    WHERE  c.post_id = ? AND c.parentComment IS NOT NULL
    ORDER  BY c.created_at ASC
    """, (post_id,)).fetchall() 
  # for listing parent and child comments nested for loop 
  # outter loop parentcomments
  # inner loop check if child's parent = current parent @ HTML
  return render_template('post.html', post=post, Parentcomments=Parentcomments, Childcomments = Childcomments, user=current_user())

@app.route('/post/<int:postId>/delete', methods=['POST'])
@login_required
def delete_post(postId):
  db = get_db()
  post = db.execute("SELECT username FROM Post WHERE postId=?",(postId,)).fetchone()
  if post and post['username'] == session['username']:
    db.execute("DELETE FROM Post WHERE postId=?", (postId,))
    db.commit()
    flash('Post deleted.', 'success')
  return redirect(url_for('feed'))

# Likes
@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_like(postId):
# def toggle_like(postId, emoji):
  db  = get_db()
  username = session['username']
  existing = db.execute(
    "SELECT like_id FROM likes WHERE postId=? AND username=?",(postId, username)
    # "SELECT like_id FROM likes WHERE postId=? AND username=? AND emoji=?",(postId, username, emoji)
  ).fetchone()
  if existing:
    db.execute("DELETE FROM likes WHERE postId=? AND username=?",(postId, username))
    liked = False
  else:
    db.execute("INSERT INTO likes (postId, username) VALUES (?,?)", (postId, username))
    # db.execute("INSERT INTO likes (postId, username) VALUES (?,?,?)",(postId, username, emoji))
    liked = True
  db.commit()
  count = db.execute(
    "SELECT COUNT(*) FROM likes WHERE postId=?", (postId,)
  ).fetchone()[0]
  return jsonify({'liked': liked, 'count': count})

# Comments
@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id, parentComment):
    content = request.form.get('content', '').strip()
    if content:
        db = get_db()
        db.execute("INSERT INTO comments (postId, username, content, parent_comment_id) VALUES (?,?,?,?)",
                   (post_id, session['username'], content, parentComment)) # HTML send back the button clicked with its parentid
        db.commit()
    return redirect(url_for('view_post', post_id=post_id))

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




