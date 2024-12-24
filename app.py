from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, g
import os
import numpy as np
import cv2
from werkzeug.utils import secure_filename
from keras.models import load_model
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'
model = load_model('model1.h5')

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

class UserDatabase:
    def __init__(self, db_name="user_accounts.db"):
        self.db_name = db_name

    def get_db(self):
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect(self.db_name)
        return db

    def close_db(self, exception=None):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()

    def create_user_table(self, username):
        with self.get_db() as conn:
            cursor = conn.cursor()
            table_name = f"user_{username}"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY,
                    date DATE,
                    time TEXT,
                    emotion TEXT
                )
            """)
            conn.commit()

    def create_users_table(self):
        with app.app_context():
            with self.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        profile_pic TEXT
                    )
                """)
                conn.commit()

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    def sign_up(self, username, password, profile_pic):
        with self.get_db() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO users (username, password, profile_pic) VALUES (?, ?, ?)", (username, password, profile_pic))
                conn.commit()
                self.create_user_table(username)
                return True, f"Sign-up successful for user '{username}'!"
            except sqlite3.IntegrityError:
                return False, f"Error: Username '{username}' already exists. Please choose another one."
    
    def update_profile_picture(self, username, profile_pic):
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET profile_pic = ? WHERE username = ?", (profile_pic, username))
            conn.commit()

    def get_profile_picture(self, username):
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT profile_pic FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
                return None

    def login(self, username, password):
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, password))
            user_id = cursor.fetchone()
            if user_id:
                return True, username
            else:
                return False, None

    def add_user_data(self, username, emotion):
        table_name = f"user_{username}"
        current_date = datetime.now().date()
        current_time = datetime.now().strftime("%H:%M")
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f"INSERT INTO {table_name} (date, time, emotion) VALUES (?, ?, ?)", (current_date, current_time, emotion))
            conn.commit()
            return f"Data added for user {username}: Date={current_date}, Time={current_time}, Emotion={emotion}"

    def get_user_data(self, username):
        table_name = f"user_{username}"
        with self.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            return rows

    def delete_user(self, username):
        table_name = f"user_{username}"
        with self.get_db() as conn:
            cursor = conn.cursor()
            try:
                # Drop the user's table
                cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                # Delete the user from users table
                cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                conn.commit()
                return True, "Your account has been deleted."
            except sqlite3.Error as e:
                conn.rollback()
                return False, f"Error deleting account: {e}"

def detect_emotions(uploaded_image):
    # Read the uploaded image
    image_array = np.frombuffer(uploaded_image.read(), np.uint8)
    img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    # Convert image to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Detect the faces
    face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)

    labels = ['Angry', 'Disgusted', 'Feared', 'Happy', 'Neutral', 'Sad', 'Surprised']
    for (x, y, w, h) in faces:
        # Extract face
        face = gray[y:y+h, x:x+w]
        # Resize face to match model's expected input size
        resized_gray_face = cv2.resize(face, (48, 48))
        yhat = model.predict(np.expand_dims(resized_gray_face / 255, 0))
        output = np.argmax(yhat)

        if output >= 0 and output < len(labels):
            return labels[output]
        else:
            return 'Undetected'

    return 'Emotion'

user_db = UserDatabase()
user_db.create_users_table()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        login_success, username = user_db.login(username, password)
        if login_success:
            return redirect(url_for('dashboard', username=username))
        else:
            flash("Invalid username or password.", "error")
    return render_template('index.html')

@app.route('/signup_form')
def signup_form():
    return render_template('signup_form.html')

@app.route('/login_form')
def login_form():
    return render_template('login_form.html')

@app.route('/signup', methods=['POST'])
def signup():
    new_username = request.form['new_username']
    new_password = request.form['new_password']

    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(request.url)

    file = request.files['file']

    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.url)

    if file and user_db.allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        signup_success, message = user_db.sign_up(new_username, new_password, filename)
        if signup_success:
            return render_template('index.html', success=message)
        else:
            return render_template('index.html', error=message)
    else:
        flash('Invalid file type. Please upload an image file.', 'error')
        return redirect(request.url)

@app.route('/dashboard/<string:username>', methods=['GET', 'POST'])
def dashboard(username):
    profile_pic = user_db.get_profile_picture(username)
    
    if request.method == 'POST':
        if 'image' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)

        file = request.files['image']

        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)

        if file and user_db.allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            user_db.update_profile_picture(username, filename)
            profile_pic = filename
            return render_template('dashboard.html', username=username, profile_pic=profile_pic, success=True)
        else:
            flash('Invalid file type. Allowed types are: png, jpg, jpeg, gif', 'error')
            return redirect(request.url)
    
    if request.method == 'POST':
        uploaded_image = request.files['image']
        emotion = detect_emotions(uploaded_image)
        if emotion != 'Undetected':
            user_db.add_user_data(username, emotion)
            return render_template('dashboard.html', success=True, username=username, emotion=emotion, profile_pic=profile_pic)
        else:
            return render_template('dashboard.html', error="Emotion could not be detected.", username=username, profile_pic=profile_pic)

    user_data = user_db.get_user_data(username)
    return render_template('dashboard.html', profile_pic=profile_pic, user_data=user_data, username=username)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/results/<string:username>')
def results(username):
    user_data = user_db.get_user_data(username)
    return render_template('results.html', user_data=user_data, username=username)

@app.route('/upload_image/<string:username>', methods=['GET', 'POST'])
def upload_image(username):
    if request.method == 'POST':
        if 'image' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        
        image = request.files['image']
        
        if image.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        
        uploaded_image = request.files['image']
        emotion = detect_emotions(uploaded_image)
        if emotion != 'Undetected':
            user_db.add_user_data(username, emotion)
            return render_template('dashboard.html', success=True, username=username, emotion=emotion)
        else:
            return render_template('dashboard.html', error="Emotion could not be detected.", username=username)

    user_data = user_db.get_user_data(username)
    return render_template('upload_image.html', username=username)

@app.route('/logout')
def logout():
    # Clear any user session data
    flash("Logged out successfully.", "success")
    return redirect(url_for('index'))

@app.route('/delete_confirmation/<string:username>')
def delete_confirmation(username):
    return render_template('delete_confirmation.html', username=username)

@app.route('/delete_account/<string:username>', methods=['POST'])
def delete_account(username):
    if request.method == 'POST':
        confirm = request.form.get('confirm')
        if confirm == 'true':
            # Delete the user account and associated data
            # Implement your deletion logic here
            user_db.delete_user(username)
            return redirect(url_for('index'))
        else:
            flash("Deletion canceled. Your account is safe.", "info")
            return redirect(url_for('dashboard', username=username))

    # Redirect to dashboard if not a POST request
    return redirect(url_for('dashboard', username=username))

if __name__ == "__main__":
    app.run(debug=True)
