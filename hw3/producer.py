import os, time, json, uuid, signal, random
from confluent_kafka import Producer
from datetime import datetime, timezone

KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:29092')
POD_ID = os.getenv('POD_ID', 'producer-default')
KEY_MODE = os.getenv('KEY_MODE', 'user_id')

# Генерация уникальных пользователей для каждого пода, чтобы гарантировать уникальность seq
USERS = [f"user_{POD_ID}_{i}" for i in range(5)]
user_seqs = {u: 0 for u in USERS}

def make_producer():
    return Producer({
        'bootstrap.servers': KAFKA_BROKERS,
        'acks': 'all',
        'enable.idempotence': True,
        'client.id': POD_ID
    })

producer = make_producer()

running = True
sent = 0
def sigterm_handler(signum, frame):
    global running
    print(f"[{POD_ID}] Received SIGTERM, shutting down...")
    running = False

signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)

def delivery_report(err, msg):
    if err is not None:
        print(f"[{POD_ID}] Delivery failed for record {msg.key()}: {err}")
    else:
        pass # Успешно отправлено

while running:
    user_id = random.choice(USERS)
    user_seqs[user_id] += 1
    seq = user_seqs[user_id]
    
    event_id = str(uuid.uuid4())
    is_poison = random.random() < 0.02
    
    event = {
        'event_id': event_id,
        'user_id': user_id,
        'type': random.choice(['page_view', 'add_to_cart', 'purchase']),
        'seq': seq,
        'produced_at': datetime.now(timezone.utc).isoformat(),
        'payload': {"poison": True} if is_poison else {"data": "some_json"},
        'is_poison': is_poison
    }
    
    key = user_id if KEY_MODE == 'user_id' else None
    
    try:
        producer.produce(
            topic='events',
            key=key,
            value=json.dumps(event),
            on_delivery=delivery_report
        )
    except BufferError:
        # Локальная очередь переполнена: ждём освобождения и пробуем снова
        producer.poll(1.0)
        continue
    except Exception as e:
        # Фатальная ошибка идемпотентного продюсера (например, после таймаутов
        # сообщений при долгой недоступности брокеров). Даём старому продюсеру
        # короткий шанс дослать очередь, затем пересоздаём и повторяем
        # отправку этого же события, чтобы не потерять seq.
        print(f"[{POD_ID}] Fatal producer error, recreating producer: {e}")
        try:
            producer.flush(5)
        except Exception:
            pass
        producer = make_producer()
        producer.produce(
            topic='events',
            key=key,
            value=json.dumps(event),
            on_delivery=delivery_report
        )
    
    producer.poll(0)
    time.sleep(1) # Скорость генерации
    sent += 1
    if sent % 30 == 0:
        print(f"[{POD_ID}] Sent {sent} events")

# Досылка всех буферизованных сообщений при остановке
print(f"[{POD_ID}] Flushing remaining messages...")
producer.flush()
print(f"[{POD_ID}] Exited gracefully.")