import os, time, json, psycopg2
from confluent_kafka import Consumer, Producer

KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:29092')
DB_DSN = os.getenv('DB_DSN', 'postgresql://user:password@localhost:5432/events_db')
POD_ID = os.getenv('POD_ID', 'consumer-default')
PROCESSING_DELAY_MS = int(os.getenv('PROCESSING_DELAY_MS', '100'))

db_conn = None
while db_conn is None:
    try:
        db_conn = psycopg2.connect(DB_DSN)
        db_conn.autocommit = True
        cursor = db_conn.cursor()
        print(f"[{POD_ID}] Successfully connected to PostgreSQL")
    except psycopg2.OperationalError:
        print(f"[{POD_ID}] Waiting for PostgreSQL to be ready...")
        time.sleep(2)

def commit_completed(err, partitions):
    if err:
        print(f"[{POD_ID}] Commit failed: {err}")

def on_partitions_assigned(c, partitions):
    print(f"[{POD_ID}] Partitions assigned: {[p.partition for p in partitions]}")

def on_partitions_revoked(c, partitions):
    # Коммитим обработанные оффсеты перед отдачей партиций
    print(f"[{POD_ID}] Partitions revoked, committing offsets...")
    try:
        c.commit(asynchronous=False)
    except Exception as e:
        print(f"[{POD_ID}] Commit on revoke failed: {e}")

consumer_conf = {
    'bootstrap.servers': KAFKA_BROKERS,
    'group.id': 'events-processor',
    'auto.offset.reset': 'earliest',
    'enable.auto.commit': False,
    'on_commit': commit_completed
}
consumer = Consumer(consumer_conf)

producer_conf = {'bootstrap.servers': KAFKA_BROKERS}
dlt_producer = Producer(producer_conf)

consumer.subscribe(['events'], on_assign=on_partitions_assigned, on_revoke=on_partitions_revoked)

def process_event(msg):
    val = json.loads(msg.value().decode('utf-8'))
    if val.get('is_poison'):
        raise ValueError("Poison pill detected")
        
    time.sleep(PROCESSING_DELAY_MS / 1000.0)
    
    try:
        cursor.execute("""
            INSERT INTO processed_events (event_id, user_id, seq, consumer_pod, topic, partition, offset_val)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (val['event_id'], val['user_id'], val['seq'], POD_ID, msg.topic(), msg.partition(), msg.offset()))
    except psycopg2.errors.UniqueViolation:
        db_conn.rollback()
        # Идемпотентная запись дедуплицирована
        cursor.execute("INSERT INTO duplicates_counter (event_id) VALUES (%s)", (val['event_id'],))
    except Exception as e:
        db_conn.rollback()
        raise e

processed = 0
while True:
    msg = consumer.poll(1.0)
    if msg is None: continue
    if msg.error():
        print(f"[{POD_ID}] Consumer error: {msg.error()}")
        continue

    attempts = 0
    success = False
    
    while attempts < 3 and not success:
        attempts += 1
        try:
            process_event(msg)
            success = True
        except Exception as e:
            print(f"[{POD_ID}] Error processing msg {msg.offset()}: {e} (Attempt {attempts})")
            if attempts == 3:
                # Отправка в DLT
                headers = {
                    'error_reason': str(e).encode(),
                    'source_topic': msg.topic().encode(),
                    'source_partition': str(msg.partition()).encode(),
                    'source_offset': str(msg.offset()).encode()
                }
                dlt_producer.produce('events.dlt', key=msg.key(), value=msg.value(), headers=headers)
                dlt_producer.flush()
                success = True # Считаем обработанным, так как ушло в DLT

    # Коммит оффсета только после успешной записи в sink или DLT
    if success:
        consumer.commit(asynchronous=False)
        processed += 1
        if processed % 30 == 0:
            print(f"[{POD_ID}] Processed {processed} events")