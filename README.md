# lidarr-cache-warmer

Cache warming tool for **Lidarr** metadata. Fetches artist and release group MBIDs from your Lidarr instance and repeatedly probes them against an API endpoint until successful, triggering cache generation in the backend.

**Dual-phase processing**: Warms artist cache first, then release group cache (only for successfully cached artists).

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
    #   FORCE_ARTISTS: "true"    # Force refresh all artists
    #   FORCE_RG: "true"         # Force refresh all release groups
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

# Per-entity cache warming attempts
max_attempts_per_artist = 25    # Artists (new cache)
max_attempts_per_rg = 15        # Release groups (depends on artists)

# API politeness settings
max_concurrent_requests = 5
rate_limit_per_second = 3
delay_between_attempts = 0.5

[run]
# Enable dual-phase processing
process_release_groups = false  # Set to true for Phase 2

[schedule]
interval_seconds = 3600         # Run every hour
max_runs = 50                   # Stop after 50 scheduled runs
```

### Key Settings

| Parameter | Purpose | Default | Notes |
|-----------|---------|---------|--------|
| **Cache Warming** |
| `max_attempts_per_artist` | Retry limit for artists | `25` | Higher = more persistent cache warming |
| `max_attempts_per_rg` | Retry limit for release groups | `15` | Lower since RGs depend on cached artists |
| `delay_between_attempts` | Wait between retries (seconds) | `0.5` | Prevents overwhelming API |
| **API Politeness** |
| `max_concurrent_requests` | Simultaneous requests | `5` | Higher = faster, but more API load |
| `rate_limit_per_second` | Max API calls per second | `3` | **Primary safety valve** |
| `circuit_breaker_threshold` | Stop after N consecutive failures | `25` | Protects against broken APIs |
| **Processing Control** |
| `process_release_groups` | Enable dual-phase processing | `false` | Set `true` for artists + albums |
| `force_artists` | Quick refresh all artists | `false` | Sets attempts to 1 for discovery |
| `force_rg` | Quick refresh all release groups | `false` | Sets attempts to 1 for discovery |
| **Storage Backend** |
| `storage_type` | Storage method | `csv` | `csv` or `sqlite` |
| `db_path` | SQLite database location | `/data/mbid_cache.db` | Used when `storage_type = sqlite` |
| **Performance** |
| `batch_size` | Entities per batch | `25` | Memory vs. progress granularity |
| `batch_write_frequency` | Save progress every N requests | `5` | Higher = less I/O, lower = safer |

### Storage Recommendations

| Library Size | Recommended Storage | Why |
|--------------|-------------------|-----|
| < 1,000 artists | `storage_type = csv` | Simple, human-readable files |
| > 1,000 artists | `storage_type = sqlite` | **Much faster**, indexed queries, atomic updates |
| > 10,000 release groups | `storage_type = sqlite` | **Essential** for reasonable performance |

**SQLite Benefits:** 30MB+ CSV becomes ~1MB database, 100x faster updates, no file corruption risk.

---

## 📊 What It Does

### First Run: Cache Discovery
On first run (no existing CSV files), the tool automatically enables **discovery mode**:
- **1 attempt per entity** to quickly survey what's already cached
- Creates baseline CSVs showing current cache state  
- **Much faster** than full cache warming on potentially cached items

### Subsequent Runs: Targeted Cache Warming

#### Phase 1: Artist Cache Warming
- Processes only artists with `status != 'success'` (pending/failed)
- Uses full attempt limits (25 by default) for intensive cache warming
- Updates `/data/mbid-artists.csv` with results

#### Phase 2: Release Group Cache Warming (Optional)
- **Only processes release groups belonging to successfully cached artists**
- Uses separate attempt limits optimized for release group caching (15 by default)
- Updates `/data/mbid-releasegroups.csv` with artist context

### Output
```
🔍 First run detected - no existing CSV files found
   Enabling force modes for initial cache discovery (1 attempt per entity)

=== Phase 1: Processing Artists ===
[1/250] Checking Artist Name [mbid] ... SUCCESS (code=200, attempts=1)  # Already cached!
[2/250] Checking Another Artist [mbid] ... TIMEOUT (code=503, attempts=1)  # Needs warming
Progress: 50/250 (20.0%) - Rate: 4.2 artists/sec - ETC: 14:32 - API: 3.00 req/sec - Batch: 30/50 success

=== Phase 2: Processing Release Groups ===
[1/120] Checking Artist Name - Album Title [mbid] ... SUCCESS (code=200, attempts=1)
```

**Subsequent runs** use full attempt limits (25 for artists, 15 for RGs) and only process pending items.

### Generated Files
- **`/data/mbid-artists.csv`** - Artist cache status tracking
- **`/data/mbid-releasegroups.csv`** - Release group cache status with artist context  
- **`/data/results_YYYYMMDDTHHMMSSZ.log`** - Simple metrics per run

---

## 📊 Statistics & Monitoring

### View Current Stats
```bash
# Get comprehensive overview
python stats.py --config /data/config.ini

# Docker version  
docker run --rm -v $(pwd)/data:/data ghcr.io/devianteng/lidarr-cache-warmer:latest python /app/stats.py --config /data/config.ini
```

**Example Output:**
```
🎵 LIDARR CACHE WARMER - STATISTICS REPORT
📋 Key Configuration Settings:
   • max_concurrent_requests: 5, rate_limit_per_second: 3
   • storage_type: sqlite, db_path: /data/mbid_cache.db

🎤 ARTIST STATISTICS:
   ✅ Successfully cached: 1,156 (94.2%)
   ❌ Failed/Timeout: 71 (5.8%)
   ⏳ Not yet processed: 0

💿 RELEASE GROUP STATISTICS:  
   ✅ Successfully cached: 8,247 (67.1%)
   🎯 Eligible for processing: 12,089 (98.4% coverage)

🚀 RECOMMENDATIONS:
   • Process 3,842 eligible release groups
   • Switch to SQLite for better performance
```

---

## 🐍 Manual Python Installation

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
python main.py --config config.ini --force-rg

# Preview what would be processed
python main.py --config config.ini --dry-run
```

---

## 🔧 Advanced Usage

### Processing Modes

**Artists Only (default):**
```ini
process_release_groups = false
```

**Dual-Phase (artists + release groups):**
```ini  
process_release_groups = true
```

### Force Refresh
Quick re-evaluation of already successful entries:
```bash
# Via environment variables (Docker)
FORCE_ARTISTS=true FORCE_RG=true docker run ...

# Via CLI (manual)
python main.py --config config.ini --force-artists --force-rg
```

### Tuning Performance
```ini
# Conservative (public APIs)
max_concurrent_requests = 3
rate_limit_per_second = 2

# Aggressive (tested APIs)  
max_concurrent_requests = 10
rate_limit_per_second = 5
max_attempts_per_artist = 50
```

---

## 💡 How It Works

Cache warming is perfect for APIs where:
1. **Backend generates data on-demand** (expensive computation)
2. **Results are cached** after first successful generation
3. **Cache misses return 503/404** until backend completes processing
4. **Repeated requests eventually succeed** when cache is ready

### Intelligent Processing
- **First run**: Quick discovery (1 attempt each) to map current cache state
- **Subsequent runs**: Intensive warming (25+ attempts) only on items that need it
- **Dependencies**: Release groups are only processed after their parent artist is successfully cached

This approach minimizes wasted effort and focuses cache warming where it's actually needed.
