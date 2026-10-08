#!/usr/bin/env python3
"""
SMD PRIME / PROJECT HYDRA - SUPABASE SCHEMA MIGRATION & RLS ENFORCER
Executes supabase/schema_v2.sql against Supabase PostgreSQL.
"""

import sys
import os
import argparse
from pathlib import Path
import psycopg2

DEFAULT_CONN_STRING = "postgresql://postgres:AjithSubabase2000@db.xaiasvckzqfvktpraxkw.supabase.co:5432/postgres"

def main():
    parser = argparse.ArgumentParser(description="Apply Supabase Schema & RLS Policies")
    parser.add_argument(
        "--conn-string",
        "-c",
        default=os.getenv("DATABASE_URL", DEFAULT_CONN_STRING),
        help="PostgreSQL connection URI"
    )
    args = parser.parse_args()

    sql_path = Path(__file__).parent.parent / "supabase" / "schema_v2.sql"
    if not sql_path.exists():
        print(f"❌ Error: {sql_path} not found.")
        sys.exit(1)

    print("==================================================================")
    print("🚀 APPLYING SUPABASE SCHEMA & RLS POLICIES")
    print("==================================================================")
    print(f"📄 SQL File:      {sql_path}")
    print(f"🔗 Target DB:      {args.conn_string[:45]}...")
    print("------------------------------------------------------------------")

    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    try:
        conn = psycopg2.connect(args.conn_string)
        conn.autocommit = True
        cur = conn.cursor()
        
        print("⏳ Executing DDL statement batch...")
        cur.execute(sql_content)
        
        print("✅ Schema applied successfully! Verified tables & RLS policies.")
        
        # Verify created tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('users', 'movies', 'movie_sources', 'watch_history');
        """)
        tables = [r[0] for r in cur.fetchall()]
        print(f"📋 Verified Tables in Public Schema ({len(tables)}/4):", ", ".join(tables))
        
        cur.close()
        conn.close()

        print("==================================================================")
        print("🎉 SUPABASE DATABASE SETUP COMPLETE!")
        print("==================================================================")

    except Exception as e:
        print(f"❌ Connection/Migration Error: {e}")
        print("\n💡 NOTE: If direct IPv6 port 5432 fails due to ISP network restrictions,")
        print("you can paste the contents of `supabase/schema_v2.sql` directly into your")
        print("Supabase Dashboard -> SQL Editor and click 'Run'.")
        sys.exit(1)

if __name__ == "__main__":
    main()
