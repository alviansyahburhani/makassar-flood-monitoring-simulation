import paho.mqtt.client as mqtt
import time
import json
import random
import threading

# --- Konfigurasi ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883

# Ambang batas ketinggian air (dalam cm) untuk status peringatan
AMBANG_AMAN = 100
AMBANG_SIAGA = 200

# Data untuk tiga sensor kita
SENSORS = [
    {
        "id": "sensor01",
        "lokasi": "Hulu Sungai Tallo",
        "topic": "sungai/tallo/sensor01/data",
        "ketinggian": 50.0,
        "lat": -5.123,
        "lon": 119.485
    },
    {
        "id": "sensor02",
        "lokasi": "Jembatan Tallo",
        "topic": "sungai/tallo/sensor02/data",
        "ketinggian": 40.0,
        "lat": -5.130,
        "lon": 119.455
    },
    {
        "id": "sensor03",
        "lokasi": "Muara Sungai Tallo",
        "topic": "sungai/tallo/sensor03/data",
        "ketinggian": 30.0,
        "lat": -5.135,
        "lon": 119.425
    }
]

def connect_mqtt(client_id):
    """Membuat dan mengembalikan client MQTT yang sudah terhubung."""
    client = mqtt.Client(client_id=client_id)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        return client
    except Exception as e:
        print(f"[{client_id}] Gagal terhubung: {e}")
        return None

def simulate_sensor(sensor_info):
    """Fungsi yang dijalankan oleh setiap thread untuk satu sensor."""
    client = connect_mqtt(f"publisher_{sensor_info['id']}")
    if not client:
        return

    client.loop_start()
    ketinggian_air = sensor_info['ketinggian']

    while True:
        try:
            # Simulasi perubahan ketinggian air
            perubahan = random.uniform(-2.0, 8.0)
            ketinggian_air += perubahan
            if ketinggian_air < 20: ketinggian_air = 20

            ketinggian_air_round = round(ketinggian_air, 1)
            kecepatan_arus = round(1 + (ketinggian_air_round / AMBANG_SIAGA) * random.uniform(0.8, 1.5), 1)

            if ketinggian_air_round < AMBANG_AMAN:
                status = "✅ Aman"
            elif AMBANG_AMAN <= ketinggian_air_round < AMBANG_SIAGA:
                status = "⚠️ Siaga"
            else:
                status = "🚨 AWAS"

            payload = {
                "id_sensor": sensor_info['id'],
                "lokasi": sensor_info['lokasi'],
                "ketinggian_air": ketinggian_air_round,
                "kecepatan_arus": kecepatan_arus,
                "status": status,
                "coords": {"lat": sensor_info['lat'], "lon": sensor_info['lon']},
                "timestamp": time.time()
            }
            
            json_payload = json.dumps(payload, ensure_ascii=False)
            client.publish(sensor_info['topic'], json_payload, qos=1)
            print(f"Kirim dari {sensor_info['id']} -> Status: {status} | Ketinggian: {ketinggian_air_round} cm")
            
            time.sleep(random.uniform(4, 6))

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error di {sensor_info['id']}: {e}")

    client.loop_stop()
    client.disconnect()

if __name__ == '__main__':
    threads = []
    print("Memulai simulasi untuk semua sensor...")
    for sensor in SENSORS:
        thread = threading.Thread(target=simulate_sensor, args=(sensor,))
        threads.append(thread)
        thread.start()

    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("\nSimulator dihentikan oleh pengguna.")
