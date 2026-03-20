from pathlib import Path
from chromadb import PersistentClient

# Use the autonomous_trading_ai project directory as base
BASE_DIR = Path(__file__).resolve().parents[1]
CHROMA_PATH = str(BASE_DIR / "chroma_data")
COLLECTION_NAME = "strategy_research"

client = PersistentClient(path=CHROMA_PATH)

# Lihat semua collection yang ada dulu
all_collections = client.list_collections()
print("Collections yang ada:")
for c in all_collections:
    print(f"  - {c.name}")

# Konfirmasi sebelum hapus
col = client.get_collection(COLLECTION_NAME)
count = col.count()
print(f"\nCollection '{COLLECTION_NAME}' berisi {count} dokumen")
print("Hapus collection ini? (y/n): ", end="")
confirm = input()

if confirm.strip().lower() == "y":
    client.delete_collection(COLLECTION_NAME)
    # Recreate kosong supaya sistem tidak crash saat startup
    client.create_collection(COLLECTION_NAME)
    print(f"Collection '{COLLECTION_NAME}' direset. Collection lain tidak tersentuh.")
else:
    print("Dibatalkan.")