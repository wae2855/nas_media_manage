import sqlite3, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from media_importer.core.db import get_enabled_dimensions

db_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tasks.db"
)
conn = sqlite3.connect(db_path, check_same_thread=False)
conn.row_factory = sqlite3.Row

dims = get_enabled_dimensions(conn)
targets = ["documentary", "restricted_level", "animation", "media_type", "broad_genre", "region"]
for d in dims:
    if d["name"] in targets:
        pm = d.get("provider_mappings", "")
        print(f"\n=== {d['name']} ===")
        print(f"  source_type: {d.get('source_type')}")
        print(f"  is_enabled: {d.get('is_enabled')}")
        print(f"  provider_mappings raw: {repr(pm[:200]) if pm else 'EMPTY'}")

        if pm:
            try:
                parsed = json.loads(pm) if isinstance(pm, str) else pm
                print(f"  parsed: {json.dumps(parsed, ensure_ascii=False)[:200]}")
                if "tmdb" in parsed:
                    print(f"  tmdb mapping: match_type={parsed['tmdb'].get('match_type')}")
                else:
                    print(f"  NO tmdb key in mapping!")
            except Exception as e:
                print(f"  PARSE ERROR: {e}")

conn.close()
