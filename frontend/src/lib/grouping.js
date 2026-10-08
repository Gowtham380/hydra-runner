/**
 * Utility for grouping multi-quality file sources into Master Movie & Web Series records.
 * Intelligently separates Movies and TV Series based on SxxExx regex parsing.
 */

function escapeXML(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, (m) => {
    switch (m) {
      case '&': return '&amp;';
      case '<': return '&lt;';
      case '>': return '&gt;';
      case '"': return '&quot;';
      case "'": return '&apos;';
      default: return m;
    }
  });
}

export function generateDynamicSVGPoster(title, genre = 'CINEMA') {
  const safeTitle = escapeXML((title || 'SMD CINEMA').toUpperCase().substring(0, 24));
  const safeGenre = escapeXML(genre.toUpperCase());
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900" viewBox="0 0 600 900">
    <defs>
      <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#1e1b4b" />
        <stop offset="50%" stop-color="#0f172a" />
        <stop offset="100%" stop-color="#020617" />
      </linearGradient>
      <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#dc2626" />
        <stop offset="100%" stop-color="#e11d48" />
      </linearGradient>
    </defs>
    <rect width="600" height="900" fill="url(#bg)" />
    <circle cx="300" cy="400" r="220" fill="#dc2626" opacity="0.08" />
    <rect x="40" y="40" width="520" height="820" rx="24" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="2" />
    <rect x="70" y="80" width="110" height="34" rx="17" fill="url(#accent)" />
    <text x="125" y="102" font-family="system-ui, sans-serif" font-weight="900" font-size="11" fill="#ffffff" text-anchor="middle" letter-spacing="2">SMD PRIME</text>
    <text x="300" y="430" font-family="system-ui, sans-serif" font-weight="900" font-size="28" fill="#ffffff" text-anchor="middle" letter-spacing="1">${safeTitle}</text>
    <text x="300" y="475" font-family="system-ui, sans-serif" font-weight="700" font-size="14" fill="#94a3b8" text-anchor="middle" letter-spacing="3">${safeGenre} • ULTRA HD</text>
  </svg>`;
  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`;
}

/**
 * Removes pirate site prefixes, Google Drive copy tags, and provider noise from titles
 */
export function cleanPiratePrefixes(rawStr) {
  if (!rawStr) return '';
  let str = rawStr.trim();

  // Multi-pass cleanup loop (up to 4 iterations for nested prefixes)
  for (let pass = 0; pass < 4; pass++) {
    const prev = str;

    // 1. Remove Google Drive copy prefixes ("Copy of ", "Copy Of ", "Copy of Copy of ")
    str = str.replace(/^(?:copy\s+of\s+)+/gi, '').trim();

    // 2. Remove full URLs (http/https/ftp)
    str = str.replace(/https?:\/\/\S+/gi, '').trim();

    // 3. Remove ANY dynamic web domain prefix at the beginning of title (e.g. www.1TamilMV.rocks, site.lease, etc.)
    str = str.replace(/^(?:https?:\/\/)?(?:www\.)?[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,10}\b\s*[-_:]?\s*/gi, '').trim();

    // 4. Remove leading Series/TV tags ("SERIES ", "TV Series ", etc.)
    str = str.replace(/^(?:series|tv\s*series|tv\s*show|web\s*series)\b\s*[-_:]?\s*/gi, '').trim();

    // 5. Remove leading provider initials / short codes ("VI ", "VT ", "DC ", "LK ", "RAI ", "SI ", "TEL ", "TAM ")
    str = str.replace(/^(?:vi|vt|dc|lk|rai|si|hd|tam|tel|hin|kan|mal|eng|sd|hq)\b\s*[-_:]?\s*/gi, '').trim();

    // 6. Remove dynamic site & brand prefixes (even without dots or separators, with trailing digits/words)
    // Catches: Movieemanhd, Movieeman, Massmovies0, Massmovies, Lk Movies2, Lkmovies, Dc Tamil, Movieztamizha, Sam Dub Lezha, Omgxmovies, Razor, Snxt, etc.
    str = str.replace(/^(?:www\s*)?(?:1?\s*tamilmv|tamilblasters|tamilrockers|movieztamizha|movieemanhd|movieeman|massmovies\d*|lkmovies\d*|lk\s*movies\d*|dctamil|dc\s*tamil|omgxmovies|sam\s*dub\s*lezha|samdub|tamilyogi|isaimini|kuttymovies|cinemavilla|bolly4u|hdhub4u|filmyzilla|desiremovies|world4ufree|snxt|razor)[a-zA-Z0-9\-\.\s]*\s*[-_:]?\s*/gi, '').trim();

    // 7. Remove any compound site words ending with 'movies', 'hd', 'tamizha', 'blasters', 'rockers', 'dub', 'lezha'
    str = str.replace(/^(?:[a-zA-Z0-9]+(?:movies|hd|tamizha|blasters|rockers|dub|lezha))\b\s*[-_:]?\s*/gi, '').trim();

    // 8. Remove leading bracketed provider or language tags like [TAM], [HINDI], [RAI], [1TamilMV], [SMD]
    str = str.replace(/^\[[^\]]+\]\s*[-_:]?\s*/gi, '').trim();

    // 9. Remove standalone leading generic words like "Movie", "Movies", "Film", "www", "hd", "tam"
    str = str.replace(/^(?:movie|movies|film|films|www|hd|tam|si|ultra hd)\s*[-_:]?\s*/gi, '').trim();

    // 10. Remove leading symbols and punctuation
    str = str.replace(/^[.\s:\-_]+/, '').trim();

    if (str === prev) break;
  }

  return str;
}

/**
 * Computes a standardized normalized grouping key for movies
 */
export function getNormalizedMovieKey(rawTitle) {
  let str = cleanPiratePrefixes(rawTitle || '');

  // 1. Remove file extensions
  str = str.replace(/\.(mkv|mp4|avi|mov|zip|rar|7z)$/i, '');

  // 2. Remove release year
  str = str.replace(/\b(19|20)\d{2}\b/g, '');

  // 3. Remove language tags
  str = str.replace(/\b(tam|tamil|tel|telugu|kan|kannada|mal|malayalam|hin|hindi|eng|english|multi|sub|esub|msub)\b/gi, '');

  // 4. Remove resolutions, codecs, containers, audio formats
  str = str.replace(/\b(1080p|720p|480p|2160p|4k|uhd|hd|sd|hevc|x264|x265|h264|h265|aac|dts|ac3|ddp5|5\.1|7\.1|web-dl|web-rip|hdrip|bluray|remux|rip)\b/gi, '');

  // 5. Remove split archive tags & release quality noise
  str = str.replace(/\b(part\s*\d+|part\d*|true|sample|proper|unrated|extended|director'?s?\s*cut|v1|v2|v3|hq|lq|hqrip|cd1|cd2)\b/gi, '');

  // 6. Remove standalone numbers/letters at end (like 25, X, 0, 00, 002)
  str = str.replace(/\b(\d+|x|a|b|c)\b/gi, '');

  // 7. Remove non-alphanumeric
  str = str.replace(/[^a-zA-Z0-9\s]/g, ' ');

  // 8. Collapse spaces
  str = str.replace(/\s+/g, ' ').trim().toLowerCase();

  // 9. Regional title alias mapping (e.g. "jana nayakudu" -> "jana nayagan")
  if (str.startsWith('jana nayak')) {
    str = str.replace('jana nayakudu', 'jana nayagan').replace('jana nayakan', 'jana nayagan');
  }

  return str || 'untitled movie';
}

/**
 * Creates clean human readable display title for a movie key
 */
export function getCleanDisplayTitle(rawTitle) {
  const normKey = getNormalizedMovieKey(rawTitle);
  if (!normKey || normKey === 'untitled movie') return cleanPiratePrefixes(rawTitle);
  
  return normKey
    .split(' ')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/**
 * Parses title to detect Series vs Movie & extracts clean base series title
 */
export function parseContentMeta(rawTitle) {
  const cleanedRaw = cleanPiratePrefixes(rawTitle || '');
  
  // 1. Full Matcher: S01E04, S1E4, S03 Ep02, S03 Ep 05, S0 Ep02, Season 1 Episode 4, S01.E04, S01_E04
  let seriesMatch = cleanedRaw.match(/(?:S|Season\s*)(\d{1,2})[\s._\-]*(?:E|Ep|Episode)?\s*(\d{1,2}(?:\.\d+)?)/i);
  let seasonNum = 1;
  let episodeNum = 1;
  let matchIndex = -1;
  let matchLength = 0;

  if (seriesMatch) {
    seasonNum = parseInt(seriesMatch[1], 10);
    episodeNum = Math.floor(parseFloat(seriesMatch[2]));
    matchIndex = seriesMatch.index;
    matchLength = seriesMatch[0].length;
  } else {
    // 2. Season-only Matcher: S01, S02 Ep, Season 2, S3 Ep Combined, S0 Ep
    const seasonOnlyMatch = cleanedRaw.match(/(?:S|Season\s*)(\d{1,2})/i);
    if (seasonOnlyMatch) {
      seasonNum = parseInt(seasonOnlyMatch[1], 10);
      matchIndex = seasonOnlyMatch.index;
      matchLength = seasonOnlyMatch[0].length;

      // Try to find episode number after season marker if present
      const remainder = cleanedRaw.substring(matchIndex + matchLength);
      const epInRemainder = remainder.match(/(?:E|Ep|Episode\s*)?\s*(\d{1,2})/i);
      if (epInRemainder && !remainder.toLowerCase().includes('gb') && !remainder.toLowerCase().includes('mb')) {
        episodeNum = parseInt(epInRemainder[1], 10);
      }
      seriesMatch = seasonOnlyMatch;
    } else {
      // 3. Episode-only Matcher: Ep 04, Episode 5, Ep05
      const epOnlyMatch = cleanedRaw.match(/(?:E|Ep|Episode\s*)\s*(\d{1,2})/i);
      if (epOnlyMatch) {
        seasonNum = 1;
        episodeNum = parseInt(epOnlyMatch[1], 10);
        matchIndex = epOnlyMatch.index;
        matchLength = epOnlyMatch[0].length;
        seriesMatch = epOnlyMatch;
      }
    }
  }

  if (seriesMatch && matchIndex !== -1) {
    // Extract base series title before season/episode marker
    let rawBase = '';
    if (matchIndex > 0) {
      rawBase = cleanedRaw.substring(0, matchIndex);
    } else {
      rawBase = cleanedRaw.substring(matchLength);
    }

    // Clean up base series title from technical tags and noise
    let base = rawBase
      .replace(/[._\-]/g, ' ')
      .replace(/\b(19|20)\d{2}\b/g, '')
      .replace(/[\(\)\[\]]/g, ' ')
      .replace(/\b(1080p|720p|480p|2160p|4k|uhd|hd|hevc|x264|x265|hdr|web-dl|hdrip|bluray|remux|tam|tamil|tel|telugu|hin|hindi|eng|english|multi|gb|mb|combined|avc|ep|episode|season)\b/gi, '')
      .replace(/\s+/g, ' ')
      .trim();

    if (base.length > 0) {
      base = base.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
    } else {
      base = 'Web Series';
    }

    // Extract Episode specific title if available after episode marker
    let epTitle = `Episode ${episodeNum}`;
    const afterEp = cleanedRaw.substring(matchIndex + matchLength).trim();
    if (afterEp.length > 0) {
      const cleanAfter = afterEp
        .replace(/\b(19|20)\d{2}\b/g, '')
        .replace(/\b(1080p|720p|480p|2160p|4k|uhd|hd|hevc|x264|x265|hdr|web-dl|hdrip|bluray|tam|tamil|tel|telugu|hin|hindi|eng|english|multi|gb|mb|combined|3gb|2gb|1gb)\b/gi, '')
        .replace(/[._\-\[\]\(\)]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      if (cleanAfter.length > 2) {
        epTitle = cleanAfter.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
      }
    }

    return {
      isSeries: true,
      season: seasonNum,
      episode: episodeNum,
      seriesTitle: base,
      episodeTitle: epTitle
    };
  }

  return {
    isSeries: false,
    season: null,
    episode: null,
    seriesTitle: null,
    episodeTitle: null
  };
}

export function groupMovies(rawMovies) {
  if (!rawMovies || !Array.isArray(rawMovies)) return [];

  const moviesMap = new Map();
  const seriesMap = new Map();

  rawMovies.forEach(item => {
    const rawTitle = item.title || item.file_name || 'Untitled';
    const meta = parseContentMeta(rawTitle);

    // Extract 4-digit release year directly from rawTitle if present
    const titleYearMatch = rawTitle.match(/\b(19|20)\d{2}\b/);
    const releaseYear = titleYearMatch ? parseInt(titleYearMatch[0], 10) : (item.release_year || 2026);

    // Determine quality label & code (Prioritize Database Columns & Theater Print Detection)
    const fname = (item.file_name || item.title || '').toLowerCase();
    let qualityCode = item.quality || '1080p';
    let qualityLabel = item.quality_label || null;

    const isPreDVD = qualityCode === 'PreDVD' || 
                     item.is_theater_print === true || 
                     item.rip_type === 'PreDVD' || 
                     item.rip_type === 'CAM/TS' || 
                     fname.includes('predvd') || 
                     fname.includes('hdcam') || 
                     fname.includes('camrip');

    if (isPreDVD) {
      qualityCode = 'PreDVD';
      qualityLabel = 'PRE-DVD THEATER';
    } else if (!qualityLabel || qualityLabel === '1080P FULL HD') {
      if (fname.includes('2160p') || fname.includes('4k') || qualityCode === '4k' || qualityCode === '2160p') {
        qualityLabel = '2160p 4K Ultra HD';
        qualityCode = '4k';
      } else if (fname.includes('720p') || qualityCode === '720p') {
        qualityLabel = '720p HD';
        qualityCode = '720p';
      } else if (fname.includes('480p') || qualityCode === '480p') {
        qualityLabel = '480p SD';
        qualityCode = '480p';
      } else {
        qualityLabel = '1080p Full HD';
        qualityCode = '1080p';
      }
    }

    // Determine language label (Prioritize Database Audio Languages)
    let language = item.audio_languages || item.language || 'Tamil';
    if (!item.audio_languages) {
      const detectedLangs = [];
      if (fname.includes('tam') || fname.includes('tamil')) detectedLangs.push('Tamil');
      if (fname.includes('tel') || fname.includes('telugu') || fname.includes('nayakudu')) detectedLangs.push('Telugu');
      if (fname.includes('kan') || fname.includes('kannada')) detectedLangs.push('Kannada');
      if (fname.includes('mal') || fname.includes('malayalam')) detectedLangs.push('Malayalam');
      if (fname.includes('hin') || fname.includes('hindi')) detectedLangs.push('Hindi');
      if (fname.includes('eng') || fname.includes('english')) detectedLangs.push('English');

      if (fname.includes('multi') || fname.includes('msub') || fname.includes('dual')) {
        language = detectedLangs.length > 0 ? detectedLangs.join(' + ') : 'Multi Audio';
      } else if (detectedLangs.length > 1) {
        language = detectedLangs.join(' + ');
      } else if (detectedLangs.length === 1) {
        language = detectedLangs[0];
      }
    }

    const sourceObj = {
      ...item,
      qualityLabel,
      qualityCode,
      ripType: item.rip_type || (isPreDVD ? 'PreDVD' : 'WEB-DL'),
      codec: item.codec || 'x264',
      isTheaterPrint: isPreDVD,
      language
    };

    if (meta.isSeries) {
      // HANDLE WEB SERIES GROUPING
      const seriesKey = meta.seriesTitle.toLowerCase().replace(/\s+/g, ' ').trim();
      const cleanSlug = seriesKey.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

      if (!seriesMap.has(seriesKey)) {
        const poster = (item.poster_url && item.poster_url.trim().length > 5) 
          ? item.poster_url 
          : generateDynamicSVGPoster(meta.seriesTitle, 'TV SERIES');

        const backdrop = (item.backdrop_url && item.backdrop_url.trim().length > 5)
          ? item.backdrop_url
          : poster;

        seriesMap.set(seriesKey, {
          master_id: item.id,
          type: 'series',
          title: meta.seriesTitle,
          slug: cleanSlug,
          poster_url: poster,
          backdrop_url: backdrop,
          release_year: releaseYear,
          rating: item.rating || 8.8,
          description: item.description || `Stream or download all seasons & episodes of ${meta.seriesTitle} in crystal clear 1080p HD.`,
          created_at: item.created_at,
          seasons: {}, // seasonNum -> episodeMap
          sources: []
        });
      }

      const series = seriesMap.get(seriesKey);
      series.sources.push(sourceObj);

      // If this item has a real image poster, prioritize it over dynamic SVG
      if (item.poster_url && !item.poster_url.startsWith('data:image/svg')) {
        series.poster_url = item.poster_url;
      }
      if (item.backdrop_url && !item.backdrop_url.startsWith('data:image/svg')) {
        series.backdrop_url = item.backdrop_url;
      }

      const sNum = meta.season;
      const eNum = meta.episode;

      if (!series.seasons[sNum]) {
        series.seasons[sNum] = {};
      }

      if (!series.seasons[sNum][eNum]) {
        series.seasons[sNum][eNum] = {
          episodeNumber: eNum,
          seasonNumber: sNum,
          title: meta.episodeTitle || `Episode ${eNum}`,
          description: `Season ${sNum} Episode ${eNum} high-definition direct cloud stream.`,
          sources: []
        };
      }

      series.seasons[sNum][eNum].sources.push(sourceObj);

    } else {
      // HANDLE MOVIE GROUPING
      const normalizedKey = getNormalizedMovieKey(rawTitle);
      const cleanTitleStr = getCleanDisplayTitle(rawTitle);
      const cleanSlug = item.slug || normalizedKey.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

      if (!moviesMap.has(normalizedKey)) {
        const poster = (item.poster_url && item.poster_url.trim().length > 5) 
          ? item.poster_url 
          : generateDynamicSVGPoster(cleanTitleStr, 'CINEMA');

        const backdrop = (item.backdrop_url && item.backdrop_url.trim().length > 5)
          ? item.backdrop_url
          : poster;

        moviesMap.set(normalizedKey, {
          master_id: item.id,
          type: 'movie',
          title: cleanTitleStr,
          slug: cleanSlug,
          poster_url: poster,
          backdrop_url: backdrop,
          release_year: releaseYear,
          rating: item.rating || 8.5,
          duration: item.duration || '2h 15m',
          description: item.description || 'High quality direct stream loaded live from 7TB SMD Prime Cloud Cinema Mesh.',
          created_at: item.created_at,
          sources: []
        });
      }

      const movie = moviesMap.get(normalizedKey);
      movie.sources.push(sourceObj);

      if (item.poster_url && !item.poster_url.startsWith('data:image/svg')) {
        movie.poster_url = item.poster_url;
      }
      if (item.backdrop_url && !item.backdrop_url.startsWith('data:image/svg')) {
        movie.backdrop_url = item.backdrop_url;
      }
    }
  });

  // Calculate total seasons and total episodes count for series & derive qualities list
  seriesMap.forEach(series => {
    const seasonNums = Object.keys(series.seasons).map(Number).sort((a, b) => a - b);
    series.seasonNumbers = seasonNums;
    series.totalSeasons = seasonNums.length;
    
    let epCount = 0;
    seasonNums.forEach(s => {
      epCount += Object.keys(series.seasons[s]).length;
    });
    series.totalEpisodes = epCount;
  });

  // Attach dynamic available_qualities array for movies directly from Supabase DB columns
  moviesMap.forEach(movie => {
    const uniqueQualitiesMap = new Map();
    movie.sources.forEach(src => {
      const qCode = src.qualityCode || src.quality || '1080p';
      const variantKey = src.id || `${qCode}_${src.qualityLabel || ''}_${src.ripType || ''}`;
      if (!uniqueQualitiesMap.has(variantKey)) {
        uniqueQualitiesMap.set(variantKey, {
          id: src.id,
          code: qCode,
          label: src.qualityLabel || src.quality_label || `${qCode.toUpperCase()} HD`,
          ripType: src.ripType || src.rip_type || '',
          codec: src.codec || '',
          language: src.language || src.audio_languages || 'Tamil',
          file_size_bytes: src.file_size_bytes,
          hf_raw_url: src.hf_raw_url,
          download_url: src.download_url,
          chunk_urls: src.chunk_urls
        });
      }
    });
    movie.available_qualities = Array.from(uniqueQualitiesMap.values());
    movie.qualities = movie.available_qualities;
  });

  // Return combined array of Movies and Series
  const moviesList = Array.from(moviesMap.values());
  const seriesList = Array.from(seriesMap.values());
  const combined = [...seriesList, ...moviesList];

  // Priority 1: Movie/Series with Real Poster available (non-SVG image URL)
  // Priority 2: SVG Poster generator fallback
  // Secondary Sort: Release Year (New to Old -> Descending: 2026, 2025, 2024...)
  return combined.sort((a, b) => {
    const aHasRealPoster = a.poster_url && !a.poster_url.startsWith('data:image/svg') && a.poster_url.trim().length > 5;
    const bHasRealPoster = b.poster_url && !b.poster_url.startsWith('data:image/svg') && b.poster_url.trim().length > 5;

    if (aHasRealPoster && !bHasRealPoster) return -1;
    if (!aHasRealPoster && bHasRealPoster) return 1;

    // Both have real posters or both have SVG posters -> Sort by release_year (New to Old)
    const yearA = parseInt(a.release_year || 2026, 10);
    const yearB = parseInt(b.release_year || 2026, 10);

    if (yearB !== yearA) {
      return yearB - yearA;
    }

    if (a.created_at && b.created_at) {
      return new Date(b.created_at) - new Date(a.created_at);
    }

    return (a.title || '').localeCompare(b.title || '');
  });
}
