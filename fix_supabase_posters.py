import re
import requests

SUPABASE_URL = "https://xaiasvckzqfvktpraxkw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhhaWFzdmNrenFmdmt0cHJheGt3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4OTQ3MjA4MSwiZXhwIjoyMTA1MDQ4MDgxfQ.q99DWsN_SdSDdwVJSE3kXlqbffHKrUXmc5NYmWEzzy8"
TMDB_KEY = "5e2c34f4d7b79e9f3a4071f5d9f25b6d"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Known poster overrides for existing movies in DB
MANUAL_POSTERS = {
    "sigma": {
        "poster_url": "https://image.tmdb.org/t/p/w500/rC7Gevz7VfU5Yw5C5B9p10A6Z.jpg", # Or high res poster
        "title": "Sigma"
    }
}

def clean_search_title(raw_title):
    # Remove brackets, resolution, episode info, language, quality tags
    q = re.sub(r'\[.*?\]|\(.*?\)', ' ', raw_title)
    q = re.sub(r'(?i)\b(s\d+e\d+|s\d+|e\d+|season|episode|ep\d+|day\d+|predvd|web-dl|webrip|hdrip|hq|hdr|1080p|720p|480p|x264|x265|hevc|aac|esub|org|clean|tam|tel|hin|mal|kan|eng|true|movie|tamil|telugu|hindi)\b', ' ', q)
    q = re.sub(r'[^a-zA-Z0-9\s]', ' ', q)
    cleaned = ' '.join(q.split()).strip()
    return cleaned or raw_title

def search_poster_omdb(query):
    try:
        url = f"https://www.omdbapi.com/?apikey=trilogy&t={requests.utils.quote(query)}"
        r = requests.get(url, timeout=4)
        if r.ok:
            data = r.json()
            if data.get("Response") == "True" and data.get("Poster") and data.get("Poster") != "N/A":
                return {
                    "poster_url": data["Poster"],
                    "backdrop_url": data["Poster"],
                    "description": data.get("Plot") if data.get("Plot") != "N/A" else f"Watch {query}",
                    "rating": float(data["imdbRating"]) if data.get("imdbRating") and data["imdbRating"] != "N/A" else 8.2
                }
    except Exception as e:
        pass
    return None

def search_poster_tmdb(query):
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={requests.utils.quote(query)}&include_adult=false"
        r = requests.get(url, timeout=4)
        if r.ok:
            results = r.json().get("results", [])
            for item in results:
                poster_path = item.get("poster_path")
                backdrop_path = item.get("backdrop_path")
                if poster_path:
                    p_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                    b_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else p_url
                    return {
                        "poster_url": p_url,
                        "backdrop_url": b_url,
                        "description": item.get("overview") or f"Watch {query}",
                        "rating": round(float(item.get("vote_average", 8.0)), 1)
                    }
    except Exception as e:
        pass
    return None

def fix_all_movies():
    print("🚀 Fetching current movies from Supabase...")
    res = requests.get(f"{SUPABASE_URL}/rest/v1/movies?select=id,title,slug,poster_url", headers=headers)
    if not res.ok:
        print("❌ Could not connect to Supabase:", res.text)
        return

    movies = res.json()
    print(f"📦 Total Movies Found in Supabase: {len(movies)}\n")

    for idx, m in enumerate(movies, 1):
        m_id = m['id']
        title = m['title']
        slug = m['slug']
        curr_poster = m.get('poster_url', '')

        search_q = clean_search_title(title)
        print(f"[{idx}/{len(movies)}] Movie: '{title}'")
        print(f"   Clean Query: '{search_q}'")

        meta = search_poster_omdb(search_q) or search_poster_tmdb(search_q)

        # Fallback to general term search if specific title didn't match
        if not meta and " " in search_q:
            first_words = " ".join(search_q.split()[:2])
            print(f"   Retry Query: '{first_words}'")
            meta = search_poster_omdb(first_words) or search_poster_tmdb(first_words)

        if meta and meta.get("poster_url"):
            print(f"   ✅ Poster Found: {meta['poster_url']}")
            patch_data = {
                "poster_url": meta["poster_url"],
                "backdrop_url": meta["backdrop_url"],
                "description": meta["description"],
                "rating": meta["rating"]
            }
            p_res = requests.patch(f"{SUPABASE_URL}/rest/v1/movies?id=eq.{m_id}", headers=headers, json=patch_data)
            if p_res.ok:
                print(f"   🎉 Supabase Updated Successfully!")
            else:
                print(f"   ❌ Update Failed: {p_res.text}")
        else:
            print(f"   ℹ️ Kept current poster fallback.")
        print("-" * 50)

if __name__ == "__main__":
    fix_all_movies()
