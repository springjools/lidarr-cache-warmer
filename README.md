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

- **`max_attempts_per_artist`**: How many times to retry each artist (default: 25)
- **`max_attempts_per_rg`**: How many times to retry each release group (default: 15)
- **`process_release_groups`**: Enable release group processing after artists complete
- **`rate_limit_per_second`**: API safety valve (default: 3 req/sec)
- **`update_lidarr`**: Set to `true` to refresh Lidarr when cache warming succeeds

---

## 📊 What It Does

### Phase 1: Artist Cache Warming
- Fetches all artists from Lidarr
- Creates `/data/mbid-artists.csv` with tracking status
- Processes artists with concurrent requests until cached or max attempts reached

### Phase 2: Release Group Cache Warming (Optional)
- Fetches all release groups (albums) from Lidarr  
- Creates `/data/mbid-releasegroups.csv` with artist context
- **Only processes release groups belonging to successfully cached artists**
- Uses separate attempt limits optimized for release group caching

### Output
```
=== Phase 1: Processing Artists ===
[1/250] Checking Artist Name [mbid] ... SUCCESS (code=200, attempts=8)
[2/250] Checking Another Artist [mbid] ... TIMEOUT (code=503, attempts=25)
Progress: 50/250 (20.0%) - Rate: 2.1 artists/sec - ETC: 14:32 - API: 3.00 req/sec - Batch: 18/25 success

=== Phase 2: Processing Release Groups ===
[1/500] Checking Artist Name - Album Title [mbid] ... SUCCESS (code=200, attempts=3)
```

### Generated Files
- **`/data/mbid-artists.csv`** - Artist cache status tracking
- **`/data/mbid-releasegroups.csv`** - Release group cache status with artist context  
- **`/data/results_YYYYMMDDTHHMMSSZ.log`** - Simple metrics per run

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

The tool keeps trying each entity until it gets a 200 response (cache hit) or exhausts attempts. This "warms" the cache so subsequent API users get fast responses.

**Dependencies**: Release groups are only processed after their parent artist is successfully cached, since RG cache generation typically requires cached artist data.
