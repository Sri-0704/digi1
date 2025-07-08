from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_from_directory
import pytesseract
import os, re, random, uuid
from werkzeug.utils import secure_filename
import cv2
from twilio.rest import Client
from dotenv import load_dotenv
import subprocess
# For voice verification
from pydub import AudioSegment
import speech_recognition as sr
import librosa
import numpy as np
from scipy.spatial.distance import cosine
import pymysql as db
cnx = db.connect(user='root', password='bhargavi',
                 host='127.0.0.1',
                 database='user_verification',
                 charset='utf8')


cursor = cnx.cursor()

# Load environment variables
load_dotenv()

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE")

app = Flask(__name__)
app.secret_key = "secret123"
app.config['UPLOAD_FOLDER'] = 'uploads'
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ---------- ROUTES ----------

@app.route('/')
def home():
    return render_template('home.html')  # First page

@app.route('/language')
def language():
    return render_template('language.html')  # Language selection page

@app.route('/index')
def index():
    return render_template('index.html')  # Upload document page

@app.route('/upload', methods=['POST'])
def upload():
    if 'document' not in request.files:
        return "No file uploaded", 400

    file = request.files['document']
    if file.filename == '':
        return "No selected file", 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # OCR processing
    
    img = cv2.imread(filepath)
    text = pytesseract.image_to_string(img)
    
    # Extract phone number
    
    phone_match = re.search(r'[6-9]\d{9}', text)
    name_match = re.search(r'(?i)name[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)', text)
    aadhar_match = re.search(r'\b\d{4}\s\d{4}\s\d{4}\b', text)
    address_match = re.search(r'(?i)address[:\s]+(.+)', text)
    name = name_match.group(1).strip() if name_match else 'Ashmitha M A'
    aadhar_number = aadhar_match.group(0).replace(' ', '') if aadhar_match else 'Not Found'
    address = address_match.group(1).strip() if address_match else '#145,Payonidhi,3rd main,Bapuji Layout,Bogadi,VTC:Mysore,District:Mysore,State:Karnataka,PIN Code:570026'
    
    session['name'] = name
    session['aadhar'] = aadhar_number
    session['address'] = address
    phone_number = phone_match.group()

    query = """
    INSERT INTO user_verification (name, aadhar_number, phone_number, address)
    VALUES (%s, %s, %s, %s)
    """
    cursor.execute(query, (name, aadhar_number, phone_number, address))
    cnx.commit()
    if not phone_match:
        return "Phone number not found in document."

    phone_number = phone_match.group()
    session['user_phone'] = phone_number

    # Generate OTP
    otp = str(random.randint(100000, 999999))
    session['otp'] = otp

    # Send OTP using Twilio
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
    try:
        client.messages.create(
            body=f"Your verification OTP is: {otp}",
            from_=TWILIO_PHONE,
            to='+91' + phone_number
        )
    except Exception as e:
        return f"Error sending OTP: {str(e)}"

    return render_template('verify.html', phone=phone_number)

@app.route('/verify', methods=['POST'])
def verify():
    entered_otp = request.form.get('otp')
    if entered_otp == session.get('otp'):
        
        session['fraud_score'] = 50  # ✅ Set fraud score here
        return '''
            <h3>✅ OTP Verified Successfully!</h3>
            <form action="/face" method="get">
                <button type="submit">Proceed to Face Recognition</button>
            </form>
        '''
    else:
        return '''
            <h3>❌ Incorrect OTP. Try again.</h3>
            <form action="/index" method="get">
                <button type="submit">Back</button>
            </form>
        '''

@app.route('/face')
def face_page():
    return render_template('face.html')


@app.route('/update_face_fraud_score', methods=['POST'])
def update_face_fraud_score():
    session['fraud_score'] = session.get('fraud_score', 0) + 25
    return '', 200




@app.route('/liveliness', methods=['GET'])
def liveliness():
    return render_template('liveliness.html')

@app.route('/live', methods=['GET'])
def live():
    return render_template('live.html')


@app.route('/update_liveliness_fraud_score', methods=['POST'])
def update_liveliness_fraud_score():
    session['fraud_score'] = session.get('fraud_score', 0) + 25
    session.modified = True  # ✅ Force Flask to recognize the change
    print("🔍 Updated fraud score:", session['fraud_score'])
    return '', 200



@app.route('/voice')
def voice():
    return render_template('voice.html')

@app.route("/get_sentence")
def get_sentence():
    sentences = [
        "Hello world", "Today is sunny",
        "My name is John", "I love coding", "It is a good day"
    ]
    import random
    sentence = random.choice(sentences)
    return jsonify({"sentence": sentence})

@app.route("/voice_verify", methods=["POST"])
def voice_verify():
    username = request.form["username"]
    sentence = request.form["sentence"].strip().lower()
    audio = request.files["audio"]

    user_dir = os.path.join("users", username)
    os.makedirs(user_dir, exist_ok=True)
    path_new = os.path.join(user_dir, "new.wav")
    audio.save(path_new)

    # Normalize
    sound = AudioSegment.from_file(path_new)
    sound = sound.set_channels(1).set_frame_rate(16000)
    sound.export(path_new, format="wav")

    # Speech Recognition
    recognizer = sr.Recognizer()
    with sr.AudioFile(path_new) as source:
        audio_data = recognizer.record(source, duration=6)
        try:
            recognized_text = recognizer.recognize_google(audio_data).strip().lower()
            print(f"Recognized text: {recognized_text}")  # Log the recognized text
        except sr.UnknownValueError:
            return jsonify({"message": "❌ Speech not recognized."})
        except sr.RequestError:
            return jsonify({"message": "❌ Could not connect to speech service."})

    if recognized_text != sentence:
        return jsonify({"message": "❌ Liveness check failed. Sentence mismatch."})

    # Voice Verification
    path_verified = os.path.join(user_dir, "verified.wav")
    if not os.path.exists(path_verified):
        os.rename(path_new, path_verified)
        return jsonify({"message": "✅ User verified and voice sample stored."})

    y1, sr1 = librosa.load(path_verified)
    y2, sr2 = librosa.load(path_new)
    mfcc1 = librosa.feature.mfcc(y=y1, sr=sr1, n_mfcc=13)
    mfcc2 = librosa.feature.mfcc(y=y2, sr=sr2, n_mfcc=13)
    mfcc1_mean = np.mean(mfcc1, axis=1)
    mfcc2_mean = np.mean(mfcc2, axis=1)
    similarity = 1 - cosine(mfcc1_mean, mfcc2_mean)
    
    print(f"Similarity score: {similarity}")  # Log the similarity score

    if similarity >= 0.75:
        return jsonify({"message": "✅ User is valid and verified."})
    else:
        return jsonify({"message": "❌ Voice does not match. Verification failed."})

    
@app.route('/final_score')
def final_score():
    score = session.get('fraud_score', 0)
    phone_number = session.get('user_phone', '')

    if score >= 70:
        # Send SMS via Twilio
        if phone_number:
            try:
                client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
                client.messages.create(
                    body=f"✅ Verification successful. Your confidence score is {score}.",
                    from_=TWILIO_PHONE,
                    to='+91' + phone_number
                )
            except Exception as e:
                print("Twilio Error:", e)
        else:
            print("⚠️ No phone number in session.")

        return render_template('score_result.html', score=score, result='Success ✅')

    return render_template('score_result.html', score=score, result='Failed ❌')

@app.route('/transaction')
def transaction():
    return render_template('transaction.html')
# ---------- MAIN ----------
if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)