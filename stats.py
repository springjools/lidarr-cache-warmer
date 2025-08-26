#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime
from typing import Dict

from main import load_config, get_lidarr_artists, get_lidarr_release_groups
from storage import create_storage_backend


def analyze_artists_stats(artists_ledger: Dict[str, Dict]) -> Dict[str, any]:
    """Analyze artist statistics from ledger"""
    if not artists_ledger:
        return {
            "total": 0,
            "success": 0,
            "timeout": 0,
            "pending": 0,
            "success_rate": 0.0
        }
    
    total = len(artists_ledger)
    success = sum(1 for r in artists_ledger.values() if r.get("status", "").lower() == "success")
    timeout = sum(1 for r in artists_ledger.values() if r.get("status", "").lower() == "timeout")
    pending = total - success - timeout
    success_rate = (success / total * 100) if total > 0 else 0.0
    
    return {
        "total": total,
        "success": success,
        "timeout": timeout,
        "pending": pending,
        "success_rate": success_rate
    }


def analyze_release_groups_stats(rg_ledger: Dict[str, Dict]) -> Dict[str, any]:
    """Analyze release group statistics from ledger"""
    if not rg_ledger:
        return {
            "total": 0,
            "success": 0,
            "timeout": 0,
            "pending": 0,
            "success_rate": 0.0,
            "eligible_for_processing": 0
        }
    
    total = len(rg_ledger)
    success = sum(1 for r in rg_ledger.values() if r.get("status", "").lower() == "success")
    timeout = sum(1 for r in rg_ledger.values() if r.get("status", "").lower() == "timeout")
    pending = total - success - timeout
    success_rate = (success / total * 100) if total > 0 else 0.0
    
    # Count RGs eligible for processing (artist successfully cached)
    eligible = sum(1 for r in rg_ledger.values() 
                  if r.get("artist_cache_status", "").lower() == "success")
    
    return {
        "total": total,
        "success": success,
        "timeout": timeout,
        "pending": pending,
        "success_rate": success_rate,
        "eligible_for_processing": eligible
    }


def format_config_summary(cfg: dict) -> str:
    """Format key configuration settings"""
    storage_type = cfg.get("storage_type", "csv")
    
    config_lines = [
        "📋 Key Configuration Settings:",
        f"   API Rate Limiting:",
        f"     • max_concurrent_requests: {cfg.get('max_concurrent_requests', 5)}",
        f"     • rate_limit_per_second: {cfg.get('rate_limit_per_second', 3)}",
        f"     • delay_between_attempts: {cfg.get('delay_between_attempts', 0.5)}s",
        f"   Cache Warming Attempts:",
        f"     • max_attempts_per_artist: {cfg.get('max_attempts_per_artist', 25)}",
        f"     • max_attempts_per_rg: {cfg.get('max_attempts_per_rg', 15)}",
        f"   Processing Options:",
        f"     • process_release_groups: {cfg.get('process_release_groups', False)}",
        f"     • batch_size: {cfg.get('batch_size', 25)}",
        f"   Storage Backend:",
        f"     • storage_type: {storage_type}",
    ]
    
    if storage_type == "sqlite":
        config_lines.append(f"     • db_path: {cfg.get('db_path', '/data/mbid_cache.db')}")
    else:
        config_lines.extend([
            f"     • artists_csv_path: {cfg.get('artists_csv_path', '/data/mbid-artists.csv')}",
            f"     • release_groups_csv_path: {cfg.get('release_groups_csv_path', '/data/mbid-releasegroups.csv')}"
        ])
    
    return "\n".join(config_lines)


def print_stats_report(cfg: dict):
    """Generate and print comprehensive stats report"""
    
    print("=" * 60)
    print("🎵 LIDARR CACHE WARMER - STATISTICS REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Configuration summary
    print(format_config_summary(cfg))
    print()
    
    # Create storage backend and load data
    try:
        storage = create_storage_backend(cfg)
        artists_ledger = storage.read_artists_ledger()
        rg_ledger = storage.read_release_groups_ledger()
    except Exception as e:
        print(f"❌ ERROR: Could not read storage: {e}")
        return
    
    # Fetch current Lidarr data for comparison
    try:
        print("📡 Fetching current data from Lidarr...")
        lidarr_artists = get_lidarr_artists(cfg["lidarr_url"], cfg["api_key"])
        lidarr_artist_count = len(lidarr_artists)
        
        if cfg.get("process_release_groups", False):
            lidarr_rgs = get_lidarr_release_groups(cfg["lidarr_url"], cfg["api_key"])
            lidarr_rg_count = len(lidarr_rgs)
        else:
            lidarr_rg_count = 0
            
    except Exception as e:
        print(f"⚠️  WARNING: Could not fetch Lidarr data: {e}")
        print("    Using ledger data only...")
        lidarr_artist_count = len(artists_ledger)
        lidarr_rg_count = len(rg_ledger)
    
    print()
    
    # Artist statistics
    artist_stats = analyze_artists_stats(artists_ledger)
    print("🎤 ARTIST STATISTICS:")
    print(f"   Total artists in Lidarr: {lidarr_artist_count:,}")
    print(f"   Artists in ledger: {artist_stats['total']:,}")
    print(f"   ✅ Successfully cached: {artist_stats['success']:,} ({artist_stats['success_rate']:.1f}%)")
    print(f"   ❌ Failed/Timeout: {artist_stats['timeout']:,}")
    print(f"   ⏳ Not yet processed: {artist_stats['pending']:,}")
    
    if lidarr_artist_count != artist_stats['total']:
        diff = lidarr_artist_count - artist_stats['total']
        print(f"   📊 Ledger sync: {abs(diff)} artists {'ahead' if diff < 0 else 'behind'} Lidarr")
    
    print()
    
    # Release group statistics (if enabled)
    if cfg.get("process_release_groups", False):
        rg_stats = analyze_release_groups_stats(rg_ledger)
        print("💿 RELEASE GROUP STATISTICS:")
        print(f"   Total release groups in Lidarr: {lidarr_rg_count:,}")
        print(f"   Release groups in ledger: {rg_stats['total']:,}")
        print(f"   ✅ Successfully cached: {rg_stats['success']:,} ({rg_stats['success_rate']:.1f}%)")
        print(f"   ❌ Failed/Timeout: {rg_stats['timeout']:,}")
        print(f"   ⏳ Not yet processed: {rg_stats['pending']:,}")
        print(f"   🎯 Eligible for processing: {rg_stats['eligible_for_processing']:,}")
        print(f"      (Release groups with successfully cached artists)")
        
        if lidarr_rg_count != rg_stats['total']:
            diff = lidarr_rg_count - rg_stats['total']
            print(f"   📊 Ledger sync: {abs(diff)} release groups {'ahead' if diff < 0 else 'behind'} Lidarr")
        
        print()
        
        # Processing efficiency insights
        if rg_stats['total'] > 0:
            eligible_percent = (rg_stats['eligible_for_processing'] / rg_stats['total']) * 100
            print("📈 PROCESSING INSIGHTS:")
            print(f"   Artist cache coverage enables {eligible_percent:.1f}% of RGs for processing")
            if artist_stats['success_rate'] < 80:
                remaining_artists = artist_stats['timeout'] + artist_stats['pending']
                print(f"   💡 Tip: {remaining_artists:,} more artists could unlock additional RGs")
        print()
    
    else:
        print("💿 RELEASE GROUP PROCESSING: Disabled")
        print("   Enable with: process_release_groups = true")
        print()
    
    # Storage efficiency
    storage_type = cfg.get("storage_type", "csv")
    total_entities = artist_stats['total'] + rg_stats.get('total', 0) if cfg.get("process_release_groups") else artist_stats['total']
    
    print("💾 STORAGE INFORMATION:")
    print(f"   Backend: {storage_type.upper()}")
    print(f"   Total entities tracked: {total_entities:,}")
    
    if storage_type == "csv" and total_entities > 1000:
        print("   💡 Tip: Consider switching to SQLite for better performance with large libraries")
        print("        storage_type = sqlite")
    elif storage_type == "sqlite":
        print("   ⚡ Optimized for large libraries with indexed queries")
    
    print()
    
    # Next steps recommendations
    print("🚀 RECOMMENDATIONS:")
    
    if artist_stats['pending'] > 0:
        print(f"   • Run cache warmer to process {artist_stats['pending']:,} pending artists")
    
    if cfg.get("process_release_groups") and rg_stats.get('pending', 0) > 0:
        eligible_pending = min(rg_stats['pending'], rg_stats['eligible_for_processing'])
        if eligible_pending > 0:
            print(f"   • Process {eligible_pending:,} eligible release groups")
    
    if artist_stats['success_rate'] > 90 and not cfg.get("process_release_groups"):
        print("   • Consider enabling release group processing: process_release_groups = true")
    
    if total_entities > 1000 and storage_type == "csv":
        print("   • Switch to SQLite for better performance: storage_type = sqlite")
    
    print()
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generate statistics report for Lidarr cache warmer"
    )
    parser.add_argument("--config", required=True, help="Path to INI config (e.g., /data/config.ini)")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
    except Exception as e:
        print(f"ERROR loading config: {e}", file=sys.stderr)
        sys.exit(2)

    print_stats_report(cfg)


if __name__ == "__main__":
    main()
