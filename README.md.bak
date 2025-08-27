# lidarr-cache-warmer

Cache warming tool for **Lidarr** metadata. Fetches artist and release group MBIDs from your Lidarr instance and repeatedly probes them against an API endpoint until successful, triggering cache generation in the backend.

**Three-phase processing**: Warms artist MBID cache first, then artist text search cache, then release group cache (each phase optional and configurable).

## Requirements

- **Lidarr instance** with API access
- **Target API** to warm (default: `https://api.lidarr.audio/api/v0.4`)
- **Docker** (recommended) or **Python 3.8+**

---

## 🐳 Docker (Recommended)

### Quick Start

```bash
# Create data directory
mkdir -p ./data

# Run container (creates config.ini and exits)
docker run --rm -v $(pwd)/data:/data ghcr.io/devianteng/lidarr-cache-warmer:latest

# Edit config with your Lidarr API key
nano ./data/config.ini

# Run the cache warmer
docker run -d --name lidarr-cache-warmer -v $(pwd)/data:/data ghcr.io/devianteng/lidarr-cache-warmer:latest

# Monitor logs
docker logs -f lidarr-cache-warmer
```

### Docker Compose

```yaml
version: '3.8'

services:
  lidarr-cache-warmer:
    image: ghcr.io/devianteng/lidarr-cache-warmer:latest
    container_name: lidarr-cache-warmer
    restart: unless-stopped
    volumes:
      - ./data:/data
    # Optional environment variables:
    # environment:
    #   FORCE_ARTISTS: "true"        # Force refresh all artists
    #   FORCE_TEXT_SEARCH: "true"    # Force refresh all text searches
    #   FORCE_RG: "true"             # Force refresh all release groups
```

---

## ⚙️ Configuration

On first run, creates `/data/config.ini`. **Edit the API key before restarting:**

```ini
[lidarr]
base_url = http://192.168.1.103:8686
api_key  = YOUR_LIDARR_API_KEY

[probe]
target_base_url = https://api.lidarr.audio/api/v0.4

# Per-phase cache warming attempts
max_attempts_per_artist = 25            # Phase 1: Artist MBID warming
max_attempts_per_artist_textsearch = 25 # Phase 2: Artist text search warming
max_attempts_per_rg = 15                # Phase 3: Release group warming

# API politeness settings
max_concurrent_requests = 5
rate_limit_per_second = 3
delay_between_attempts = 0.5

[run]
# Enable/disable each processing phase
process_artist_textsearch = true  # Phase 2: Artist text search warming
process_release_groups = false    # Phase 3: Release group warming

[schedule]
interval_seconds = 3600         # Run every hour
max_runs = 50                   # Stop after 50 scheduled runs
```

### Key Settings

| Parameter | Purpose | Default | Notes |
|-----------|---------|---------|--------|
| **Cache Warming Phases** |
| `max_attempts_per_artist` | MBID retry limit for artists | `25` | Phase 1: Direct artist lookups |
| `max_attempts_per_artist_textsearch` | Text search retry limit | `25` | Phase 2: Search-by-name warming |
| `max_attempts_per_rg` | Retry limit for release groups | `15` | Phase 3: Album cache warming |
| **Processing Control** |
| `process_artist_textsearch` | Enable text search warming | `true` | Warms search-by-name cache |
| `process_release_groups` | Enable release group warming | `false` | Depends on successful artists |
| **Force Refresh Options** |
| `force_artists` | Re-check successful artists | `false` | Sets attempts to 1 for discovery |
| `force_text_search` | Re-check successful searches | `false` | Re-warms search cache |
| `force_rg` | Re-check successful release groups | `false` | Sets attempts to 1 for discovery |
| **API Politeness** |
| `max_concurrent_requests` | Simultaneous requests | `5` | Higher = faster, but more API load |
| `rate_limit_per_second` | Max API calls per second | `3` | **Primary safety valve** |
| `delay_between_attempts` | Wait between retries (seconds) | `0.5` | Prevents overwhelming API |
| **Storage Backend** |
| `storage_type` | Storage method | `csv` | `csv` or `sqlite` |
| `db_path` | SQLite database location | `/data/mbid_cache.db` | Used when `storage_type = sqlite` |

### Storage Recommendations

| Library Size | Recommended Storage | Why |
|--------------|-------------------|-----|
| < 1,000 artists | `storage_type = csv` | Simple, human-readable files |
| > 1,000 artists | `storage_type = sqlite` | **Much faster**, indexed queries, atomic updates |
| > 10,000 entities | `storage_type = sqlite` | **Essential** for reasonable performance |

**SQLite Benefits:** 30MB+ CSV becomes ~1MB database, 100x faster updates, no file corruption risk, optimized text search tracking.

---

## 📊 What It Does

### Three-Phase Cache Warming Process

The tool operates in up to three distinct phases, each targeting different API cache systems:

#### Phase 1: Artist MBID Cache Warming (Always Enabled)
- **Purpose**: Warms direct artist lookup cache using MusicBrainz IDs
- **Endpoint**: `GET /artist/{mbid}`
- **When**: Always runs first - foundation for all other phases
- **Retry Logic**: Up to 25 attempts per artist by default
- **Output**: Updates artist `status` in storage

#### Phase 2: Artist Text Search Cache Warming (Optional, Default: Enabled)
- **Purpose**: Warms search-by-name cache for user queries like "metallica" 
- **Endpoint**: `GET /search?type=all&query={artist_name}`
- **When**: After Phase 1, for all artists with names
- **Retry Logic**: Up to 25 attempts per text search by default
- **Benefits**: Faster response times for user searches in Lidarr
- **Output**: Updates `text_search_attempted` and `text_search_success` flags

#### Phase 3: Release Group Cache Warming (Optional, Default: Disabled)
- **Purpose**: Warms album/release group cache using MusicBrainz IDs
- **Endpoint**: `GET /album/{rg_mbid}`
- **When**: Only after Phase 1 completes successfully for the parent artist
- **Dependency**: Requires successful artist cache warming first
- **Output**: Updates release group `status` in storage

### First Run: Cache Discovery
On first run (no existing storage), the tool automatically enables **discovery mode**:
- **1 attempt per entity** to quickly survey what's already cached
- **Text search disabled** on first run to prioritize MBID cache building
- Creates baseline storage showing current cache state  
- **Much faster** than full cache warming on potentially cached items

### Subsequent Runs: Targeted Cache Warming

```
🔍 First run detected - no existing storage found
   Enabling force modes for initial cache discovery (1 attempt per entity)

=== Phase 1: Artist MBID Cache Warming ===
[1/250] Checking Artist Name [mbid] ... SUCCESS (code=200, attempts=1)  # Already cached!
[2/250] Checking Another Artist [mbid] ... TIMEOUT (code=503, attempts=1)  # Needs warming
Progress: 50/250 (20.0%) - Rate: 4.2 artists/sec - ETC: 14:32 - API: 3.00 req/sec - Batch: 30/50 success

=== Phase 2: Artist Text Search Cache Warming ===
[1/200] Text search for Metallica ... SUCCESS (code=200, attempts=1)
[2/200] Text search for Bob Dylan ... TIMEOUT (code=503, attempts=3)  # Cache building
Progress: 50/200 (25.0%) - Rate: 3.8 searches/sec - ETC: 12:45 - API: 3.00 req/sec - Batch: 45/50 success

=== Phase 3: Release Group Cache Warming ===
[1/120] Checking Artist Name - Album Title [mbid] ... SUCCESS (code=200, attempts=1)
```

**Subsequent runs** use full attempt limits and only process pending/failed items.

### Generated Files
- **`/data/mbid-artists.csv`** - Artist cache status with text search tracking
- **`/data/mbid-releasegroups.csv`** - Release group cache status with artist context  
- **`/data/results_YYYYMMDDTHHMMSSZ.log`** - Simple metrics per run

### Text Search Cache Benefits

Text search warming provides significant user experience improvements:
- **Faster search results** when users search for artists by name in Lidarr
- **Reduced API load** during peak usage times  
- **Improved responsiveness** for music discovery workflows
- **Proactive caching** before users actually search

Example: Without text search warming, searching "metallica" might take 2-3 seconds while the cache builds. With warming, results appear instantly.

---

## 📊 Statistics & Monitoring

### View Current Stats
```bash
# Get comprehensive overview with Docker
docker run --rm -v $(pwd)/data:/data --entrypoint python ghcr.io/devianteng/lidarr-cache-warmer:latest /app/stats.py --config /data/config.ini

# Manual Python installation
python stats.py --config /data/config.ini
```

**Example Output:**
```
🎵 LIDARR CACHE WARMER - STATISTICS REPORT
📋 Key Configuration Settings:
   • max_concurrent_requests: 5, rate_limit_per_second: 3
   • process_artist_textsearch: true, max_attempts_per_artist_textsearch: 25
   • storage_type: sqlite, db_path: /data/mbid_cache.db

🎤 ARTIST MBID STATISTICS:
   ✅ Successfully cached: 1,156 (94.2%)
   ❌ Failed/Timeout: 71 (5.8%)
   ⏳ Not yet processed: 0

🔍 ARTIST TEXT SEARCH STATISTICS:
   Artists with names: 1,245
   ✅ Text searches attempted: 1,200 (96.4%)
   ✅ Text searches successful: 1,180 (98.3%)
   📊 Text search coverage: 96.4% of named artists

💿 RELEASE GROUP STATISTICS:  
   ✅ Successfully cached: 8,247 (67.1%)
   🎯 Eligible for processing: 12,089 (98.4% coverage)

🚀 RECOMMENDATIONS:
   • Process 45 pending text searches
   • Process 3,842 eligible release groups  
   • Next run will execute: Phase 2: Text search warming, Phase 3: Release group warming
```

---

## 🔧 Manual Python Installation

```bash
# Clone and setup
git clone https://github.com/devianteng/lidarr-cache-warmer.git
cd lidarr-cache-warmer
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run once (creates config.ini)
python main.py --config config.ini

# Edit config.ini with your Lidarr API key, then:
python main.py --config config.ini

# Or run on schedule:
python entrypoint.py

# View statistics:
python stats.py --config config.ini
```

### CLI Options
```bash
# Force refresh modes (sets attempts to 1 for quick check)
python main.py --config config.ini --force-artists
python main.py --config config.ini --force-text-search  # NEW
python main.py --config config.ini --force-rg

# Preview what would be processed
python main.py --config config.ini --dry-run
```

---

## 🔧 Advanced Usage

### Processing Modes

**Artists Only:**
```ini
process_artist_textsearch = false
process_release_groups = false
```

**Artists + Text Search (Recommended):**
```ini  
process_artist_textsearch = true
process_release_groups = false
```

**Full Three-Phase Processing:**
```ini
process_artist_textsearch = true
process_release_groups = true
```

### Force Refresh
Quick re-evaluation of already successful entries:
```bash
# Via environment variables (Docker)
FORCE_ARTISTS=true FORCE_TEXT_SEARCH=true FORCE_RG=true docker run ...

# Via CLI (manual)
python main.py --config config.ini --force-artists --force-text-search --force-rg
```

### Tuning Performance
```ini
# Conservative (public APIs, shared hosting)
max_concurrent_requests = 3
rate_limit_per_second = 2
max_attempts_per_artist = 15
max_attempts_per_artist_textsearch = 10

# Aggressive (private APIs, dedicated servers)  
max_concurrent_requests = 10
rate_limit_per_second = 5
max_attempts_per_artist = 50
max_attempts_per_artist_textsearch = 30
```

### Text Search Optimization
```ini
# Disable text search for bandwidth-constrained environments
process_artist_textsearch = false

# Quick text search discovery (faster, less thorough)
max_attempts_per_artist_textsearch = 5

# Intensive text search warming (slower, more thorough)  
max_attempts_per_artist_textsearch = 50
```

---

## 💡 How It Works

Cache warming is perfect for APIs where:
1. **Backend generates data on-demand** (expensive computation/database queries)
2. **Results are cached** after first successful generation
3. **Cache misses return 503/404** until backend completes processing
4. **Repeated requests eventually succeed** when cache is ready

### Intelligent Processing
- **First run**: Quick discovery (1 attempt each) to map current cache state
- **Subsequent runs**: Intensive warming (25+ attempts) only on items that need it
- **Phase dependencies**: Text search and release groups only processed after their dependencies succeed
- **Smart retry logic**: Different retry strategies for different types of cache misses

### Text Search Cache Warming Strategy
The text search feature specifically targets the search-by-name cache system:

1. **URL Encoding**: Properly handles special characters in artist names
2. **Query Format**: Uses `?type=all&query={artist_name}` format for comprehensive results  
3. **Cache Building**: Retries 503 responses as the search index builds
4. **Success Tracking**: Records both attempt status and success status for analytics

This approach minimizes wasted effort and focuses cache warming where it provides maximum user benefit.

---

## 🔄 Migration from Previous Versions

### Existing Users
The text search feature is **fully backward compatible**:
- **Existing CSV/SQLite files** work without modification
- **New text search fields** are added automatically
- **Default settings** enable text search warming
- **No breaking changes** to existing configuration

### Storage Migration
When upgrading, the tool automatically:
- **CSV**: Adds new columns for text search tracking  
- **SQLite**: Adds new fields and indexes for text search data
- **Preserves** all existing artist and release group data
- **Populates** text search fields with appropriate defaults

No manual migration steps required!
