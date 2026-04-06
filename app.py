import hashlib
import sqlite3
import os
from datetime import datetime
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for, session, jsonify, flash)

DATABASE = 'hkugram.db'
SECRET_KEY = 'hkugram_comp3278'

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Database
def get_db() -> sqlite3.Connection:
  db = g._database = sqlite3.connect(DATABASE)
  db.row_factory = sqlite3.Row
  db.execute("PRAGMA foreign_keys = ON")
  return db

@app.teardown_appcontext
def close_db(_):
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
    if 'username' not in session:
      return redirect(url_for('login'))
    return f(*args, **kwargs)
  return decorated

def current_user():
  if 'username' not in session:
    return None
  db = get_db()
  return db.execute("SELECT * FROM User WHERE username=?", (session['username'],)).fetchone()



# root
@app.route('/')
def index():
  if 'username' in session:
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
      session['username'] = user['username']
      return redirect(url_for('index'))
      
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

# Posts


# Likes


# Comments




if __name__ == '__main__':
  if not os.path.exists(DATABASE):
    init_db()
  else:
    # still apply any new schema changes
    with app.app_context():
      db = get_db()
      with open('schema.sql') as f:
        db.executescript(f.read())
      db.commit()
  app.run(debug=True, port=5000, threaded=True)




