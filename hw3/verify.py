import os, psycopg2, json
from datetime import datetime
from confluent_kafka import Consumer

print(f"GitHub: Andrey-Pavlovich-Kalmykov, Time: {datetime.now()}")

DB_DSN = os.getenv('DB_DSN', 'postgresql://user:password@localhost:5432/events_db')
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:29092')

db_conn = psycopg2.connect(DB_DSN)
cursor = db_conn.cursor()

# Чтение events.dlt
dlt_consumer = Consumer({
    'bootstrap.servers': KAFKA_BROKERS,
    'group.id': 'verifier',
    'auto.offset.reset': 'earliest'
})
dlt_consumer.subscribe(['events.dlt'])
dlt_events = set()
empty_polls = 0
# Читаем весь events.dlt: конец топика определяем по серии пустых poll'ов
while empty_polls < 10:
    msg = dlt_consumer.poll(0.5)
    if msg is None or msg.error():
        empty_polls += 1
    else:
        empty_polls = 0
        val = json.loads(msg.value().decode('utf-8'))
        dlt_events.add((val['user_id'], val['seq']))
dlt_consumer.close()

cursor.execute("SELECT COUNT(*) FROM duplicates_counter;")
dupes = cursor.fetchone()[0]
print(f"\nDuplicates discarded: {dupes}")

cursor.execute("SELECT user_id, array_agg(seq ORDER BY seq) FROM processed_events GROUP BY user_id;")
users_data = cursor.fetchall()

total_gaps = 0
for user_id, seqs in users_data:
    if not seqs: continue
    max_seq = max(seqs)
    expected_seqs = set(range(1, max_seq + 1))
    actual_seqs = set(seqs)
    missing = expected_seqs - actual_seqs
    
    # Событие не потеряно, если оно в DLT
    missing_not_in_dlt = [s for s in missing if (user_id, s) not in dlt_events]
    total_gaps += len(missing_not_in_dlt)

print(f"Unexplained gaps (not in DLT): {total_gaps}")

# Проверка нарушения порядка
cursor.execute("""
    SELECT count(*) FROM (
        SELECT user_id, seq, processed_at, 
               lag(seq) over (partition by user_id order by processed_at) as prev_seq
        FROM processed_events
    ) t
    WHERE prev_seq > seq;
""")
out_of_order = cursor.fetchone()[0]
print(f"Out of order recordings: {out_of_order}")