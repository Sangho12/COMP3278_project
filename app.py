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


# user authentication - register


# user authentication - logout


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




