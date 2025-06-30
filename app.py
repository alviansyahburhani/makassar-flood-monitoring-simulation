import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, session, redirect, url_for, request, flash
from flask_socketio import SocketIO
from flask_mqtt import Mqtt
import json
import random
import string
import ssl
import os
from collections import deque
from datetime import datetime

# --- Konfigurasi Aplikasi ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24) # Diperlukan untuk session management

# --- Konfigurasi User untuk Login Web ---
WEB_USERNAME = 'admin'
WEB_PASSWORD = 'banjir123'

# --- Konfigurasi MQTT ---
app.config['MQTT_BROKER_URL'] = 'broker.hivemq.com'
app.config['MQTT_BROKER_PORT'] = 8883
app.config['MQTT_USERNAME'] = 'userbanjir'
app.config['MQTT_PASSWORD'] = 'passwordrahasia123'
app.config['MQTT_TLS_ENABLED'] = True
app.config['MQTT_TLS_VERSION'] = ssl.PROTOCOL_TLS
app.config['MQTT_CLIENT_ID'] = f'pusat-kendali-banjir-server'

MQTT_TOPIC = "sungai/tallo/+/data"

# --- Inisialisasi Ekstensi ---
socketio = SocketIO(app)
mqtt = Mqtt(app)

# --- Variabel Global untuk State Aplikasi ---
sensor_statuses = {}
event_logs = deque(maxlen=20) # Simpan 20 log terakhir

# --- Rute untuk Autentikasi Web (Fitur #1) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == WEB_USERNAME and password == WEB_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau Password salah!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# --- Rute Aplikasi Utama ---
@app.route('/')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('index.html')

# --- Logika Socket.IO (Terhubung ke Frontend) ---
@socketio.on('connect')
def handle_socket_connect():
    if not session.get('logged_in'):
        return False # Tolak koneksi socket jika belum login
    print("Dashboard terhubung ke Pusat Data!")
    # Kirim log yang sudah ada ke client yang baru terhubung
    socketio.emit('initial_logs', list(event_logs))

# --- Logika MQTT (Terhubung ke Sensor) ---
@mqtt.on_connect()
def handle_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Pusat Data terhubung ke Broker MQTT!")
        mqtt.subscribe(MQTT_TOPIC)
    else:
        print(f"Gagal terhubung ke MQTT, kode: {rc}")

@mqtt.on_message()
def handle_mqtt_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode('utf-8'))
        sensor_id = data.get('id_sensor')
        if not sensor_id: return

        # Validasi Input (Sudah ada sebelumnya)
        ketinggian = data.get('ketinggian_air')
        if not isinstance(ketinggian, (int, float)) or not (0 <= ketinggian <= 1000):
            print(f"Data ketinggian tidak valid dari {sensor_id} diterima: {ketinggian}")
            return
        
        print(f"Terima data dari {sensor_id} <- {data.get('status', 'N/A')}")
        socketio.emit('update_sensor', data)

        # --- Logika untuk Riwayat Kejadian (Fitur #3) ---
        previous_status = sensor_statuses.get(sensor_id)
        new_status = data.get('status')
        if new_status and new_status != previous_status:
            timestamp = datetime.now().strftime('%H:%M:%S')
            log_message = f"[{timestamp}] Sensor '{data.get('lokasi')}' berubah status menjadi: {new_status}"
            event_logs.appendleft(log_message) # Tambahkan ke paling atas
            socketio.emit('new_log', log_message)

        # Update status terakhir sensor
        sensor_statuses[sensor_id] = new_status
        
        # --- Logika untuk Ringkasan Sistem (Fitur #2) ---
        total_sensors = len(sensor_statuses)
        status_counts = {"AWAS": 0, "Siaga": 0, "Aman": 0}
        highest_status_level = 0
        highest_status_name = "Aman"

        status_map = {"AWAS": 3, "Siaga": 2, "Aman": 1}

        for status in sensor_statuses.values():
            if "AWAS" in status:
                status_counts["AWAS"] += 1
            elif "Siaga" in status:
                status_counts["Siaga"] += 1
            elif "Aman" in status:
                status_counts["Aman"] += 1
        
        if status_counts["AWAS"] > 0:
            highest_status_level = 3
            highest_status_name = "AWAS"
        elif status_counts["Siaga"] > 0:
            highest_status_level = 2
            highest_status_name = "Siaga"
        
        summary = {
            "total_sensors": total_sensors,
            "counts": status_counts,
            "highest_status": highest_status_name
        }
        socketio.emit('system_summary', summary)

    except Exception as e:
        print(f"Error memproses pesan: {e}")

# --- Menjalankan Aplikasi ---
if __name__ == '__main__':
    print(f"Server Sistem Peringatan Dini Banjir berjalan. Buka browser dan akses halaman login.")
    socketio.run(app, host='0.0.0.0', port=5001, debug=False)