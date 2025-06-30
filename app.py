import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from flask_mqtt import Mqtt
import json
import random
import string
import requests # Library untuk melakukan HTTP request ke Gemini API

# --- Konfigurasi Gemini API ---
# Di lingkungan nyata, ini harus disimpan sebagai environment variable
# Untuk saat ini, kita biarkan kosong karena akan di-handle oleh environment Canvas
API_KEY = "" 
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"

def generate_client_id(length=8):
    return ''.join(random.choice(string.ascii_lowercase) for i in range(length))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kunci-rahasia-banjir-multi!'
app.config['MQTT_BROKER_URL'] = 'broker.hivemq.com'
app.config['MQTT_BROKER_PORT'] = 1883
app.config['MQTT_USERNAME'] = ''
app.config['MQTT_PASSWORD'] = ''
app.config['MQTT_CLIENT_ID'] = f'pusat-data-banjir-{generate_client_id()}'

MQTT_TOPIC = "sungai/tallo/+/data"

socketio = SocketIO(app)
mqtt = Mqtt(app)

# State untuk melacak apakah laporan sudah dibuat untuk status AWAS saat ini
laporan_awas_dibuat = False

# --- Fungsi untuk memanggil Gemini API ---
def get_gemini_recommendation(sensor_data):
    global laporan_awas_dibuat
    laporan_awas_dibuat = True # Tandai bahwa laporan sedang dibuat

    prompt = f"""
    Anda adalah sistem ahli untuk penanggulangan bencana banjir.
    Data sensor berikut menunjukkan kondisi darurat:
    - Lokasi: {sensor_data['lokasi']}
    - Ketinggian Air: {sensor_data['ketinggian_air']} cm
    - Kecepatan Arus: {sensor_data['kecepatan_arus']} m/s
    - Status: AWAS

    Berdasarkan data ini, berikan laporan taktis dalam format JSON yang ketat sesuai skema. Jangan tambahkan markdown.
    """

    # Skema JSON untuk output yang terstruktur dari Gemini
    json_schema = {
        "type": "OBJECT",
        "properties": {
            "analisis_singkat": { "type": "STRING" },
            "rekomendasi_tindakan": {
                "type": "ARRAY",
                "items": { "type": "STRING" }
            },
            "pesan_untuk_warga": { "type": "STRING" }
        },
        "required": ["analisis_singkat", "rekomendasi_tindakan", "pesan_untuk_warga"]
    }

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": json_schema
        }
    }

    try:
        response = requests.post(GEMINI_API_URL, json=payload)
        response.raise_for_status() # Lemparkan error jika status code bukan 2xx
        result = response.json()
        
        # Ekstrak teks JSON dari respons Gemini
        report_text = result['candidates'][0]['content']['parts'][0]['text']
        report_json = json.loads(report_text)
        
        print("Laporan dari Gemini diterima:", report_json)
        socketio.emit('gemini_report', report_json)
    except requests.exceptions.RequestException as e:
        print(f"Error saat memanggil Gemini API: {e}")
        socketio.emit('gemini_error', {"error": "Gagal menghubungi AI Assistant."})
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error mem-parsing respons Gemini: {e}")
        socketio.emit('gemini_error', {"error": "Gagal memahami respons dari AI."})


@app.route('/')
def index():
    return render_template('index.html')

@mqtt.on_connect()
def handle_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Pusat Data terhubung ke Broker MQTT!")
        mqtt.subscribe(MQTT_TOPIC)
        print(f"Mendengarkan semua sensor di topik: {MQTT_TOPIC}")
    else:
        print("Gagal terhubung ke MQTT.")

@mqtt.on_message()
def handle_mqtt_message(client, userdata, message):
    global laporan_awas_dibuat
    try:
        payload_str = message.payload.decode('utf-8')
        data = json.loads(payload_str)
        print(f"Terima data dari {data.get('id_sensor', 'Unknown')} <- {data.get('status', 'N/A')}")
        
        socketio.emit('update_sensor', data)

        # Cek jika status AWAS dan laporan belum dibuat
        if "AWAS" in data.get('status', '') and not laporan_awas_dibuat:
            print("Status AWAS terdeteksi! Meminta laporan dari Gemini...")
            socketio.emit('generating_report') # Beri tahu UI untuk menampilkan loading
            # Panggil Gemini di thread terpisah agar tidak memblokir
            socketio.start_background_task(get_gemini_recommendation, data)
        
        # Reset flag jika status sudah tidak AWAS
        if "AWAS" not in data.get('status', '') and laporan_awas_dibuat:
            laporan_awas_dibuat = False
            print("Kondisi kembali aman, flag laporan direset.")

    except Exception as e:
        print(f"Error memproses pesan: {e}")

@socketio.on('connect')
def handle_socket_connect():
    print("Dashboard terhubung ke Pusat Data!")

if __name__ == '__main__':
    print("Server Sistem Peringatan Dini Banjir berjalan di http://127.0.0.1:5001")
    socketio.run(app, host='0.0.0.0', port=5001, use_reloader=False, debug=True)
