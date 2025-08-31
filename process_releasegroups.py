#!/usr/bin/env python3
import asyncio
import random
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import aiohttp

from storage import iso_now
from bcolors import bcolors
from colors import Colors
colored_output = True

class SafeRateLimiter:
    """Production-safe rate limiter with circuit breaker and backoff"""

    def __init__(
        self,
        requests_per_second: float = 3.0,
        max_concurrent: int = 5,
        circuit_breaker_threshold: int = 25,
        backoff_factor: float = 0.5,
        max_backoff_seconds: float = 30.0
    ):
        self.base_rate = requests_per_second
        self.current_rate = requests_per_second
        self.max_concurrent = max_concurrent

        # Rate limiting
        self.request_times = deque()
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Circuit breaker
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.consecutive_failures = 0
        self.last_failure_time = 0
        self.backoff_factor = backoff_factor
        self.max_backoff_seconds = max_backoff_seconds

        # Statistics
        self.total_requests = 0
        self.total_successes = 0
        self.total_rate_limits = 0
        self.total_errors = 0
        self.circuit_breaker_trips = 0

    async def acquire(self) -> bool:
        """Acquire permission to make a request. Returns False if circuit breaker is open."""
        if self._is_circuit_breaker_open():
            return False

        await self.semaphore.acquire()

        try:
            await self._rate_limit()
            self.total_requests += 1
            return True
        except Exception:
            self.semaphore.release()
            raise

    def release(self, status_code: int, response_time_seconds: float):
        """Release the semaphore and record the result"""
        self.semaphore.release()

        if status_code == 200:
            self.total_successes += 1
            self.consecutive_failures = 0
            # Gradually restore rate after success
            if self.current_rate < self.base_rate:
                self.current_rate = min(self.current_rate * 1.05, self.base_rate)

        elif status_code == 429:  # Rate limited - this is bad, reduce rate
            self.total_rate_limits += 1
            self.consecutive_failures += 1
            self.last_failure_time = time.time()
            self.current_rate *= 0.5
            print(f"{bcolors.WARNING}⚠️  Rate limited! Reducing rate to {self.current_rate:.2f} req/sec{bcolors.ENDC}")

        elif status_code in (0, "TIMEOUT") or str(status_code).startswith("EXC:"):  # Connection issues
            self.total_errors += 1
            self.consecutive_failures += 1
            self.last_failure_time = time.time()
            self.current_rate *= 0.8
            print(f"{bcolors.WARNING}⚠️  Connection error {status_code}! Reducing rate to {self.current_rate:.2f} req/sec{bcolors.ENDC}")

        # For cache warming: 503, 404, and other HTTP errors are EXPECTED
        # Don't reduce rate for these - they're part of normal cache warming process
        else:
            self.consecutive_failures = 0  # Reset failures for expected responses

    async def _rate_limit(self):
        """Implement token bucket rate limiting"""
        now = time.time()

        # Remove old request timestamps
        while self.request_times and now - self.request_times[0] > 1.0:
            self.request_times.popleft()

        # Check if we're at the rate limit
        if len(self.request_times) >= self.current_rate:
            oldest_request = self.request_times[0]
            wait_time = 1.0 - (now - oldest_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                now = time.time()
                while self.request_times and now - self.request_times[0] > 1.0:
                    self.request_times.popleft()

        self.request_times.append(now)

    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker should prevent requests"""
        if self.consecutive_failures < self.circuit_breaker_threshold:
            return False

        time_since_failure = time.time() - self.last_failure_time
        backoff_time = min(
            self.backoff_factor ** (self.consecutive_failures - self.circuit_breaker_threshold),
            self.max_backoff_seconds
        )

        if time_since_failure < backoff_time:
            self.circuit_breaker_trips += 1
            return True

        # Try to reset circuit breaker
        self.consecutive_failures = max(0, self.consecutive_failures - 1)
        return False

    def get_stats(self) -> dict:
        """Get current statistics"""
        success_rate = (self.total_successes / self.total_requests) if self.total_requests > 0 else 0

        return {
            "total_requests": self.total_requests,
            "success_rate": f"{success_rate:.1%}",
            "rate_limits_hit": self.total_rate_limits,
            "server_errors": self.total_errors,
            "current_rate": f"{self.current_rate:.2f} req/sec",
            "circuit_breaker_failures": self.consecutive_failures,
            "circuit_breaker_trips": self.circuit_breaker_trips,
            "circuit_breaker_open": self._is_circuit_breaker_open()
        }


async def check_release_group_with_cache_warming(
    session: aiohttp.ClientSession,
    rg_mbid: str,
    target_base_url: str,
    max_attempts: int = 15,
    delay_between_attempts: float = 0.5,
    timeout: int = 10
) -> Tuple[str, str, int, float]:
    """Check single release group MBID with cache warming - keep trying until success or max attempts"""
    url = f"{target_base_url.rstrip('/')}/album/{rg_mbid}"
    total_response_time = 0

    for attempt in range(max_attempts):
        start_time = time.time()
        try:
            async with session.get(url) as resp:
                response_time = time.time() - start_time
                total_response_time += response_time
                status_code = resp.status

                if status_code == 200:
                    return "success", str(status_code), attempt + 1, total_response_time

        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            total_response_time += response_time
            status_code = "TIMEOUT"
        except Exception as e:
            response_time = time.time() - start_time
            total_response_time += response_time
            status_code = f"EXC:{type(e).__name__}"

        if attempt < max_attempts - 1:
            await asyncio.sleep(delay_between_attempts)

    return "timeout", str(status_code), max_attempts, total_response_time


async def check_release_groups_concurrent_with_timing(
    to_check: List[str],
    ledger: Dict[str, Dict],
    cfg: dict,
    storage,
    overall_start_time: float,
    offset: int
) -> Tuple[int, int, int]:
    """Check release group MBIDs concurrently with proper timing across batches"""

    rate_limiter = SafeRateLimiter(
        requests_per_second=cfg["rate_limit_per_second"],
        max_concurrent=cfg["max_concurrent_requests"],
        circuit_breaker_threshold=cfg["circuit_breaker_threshold"],
        backoff_factor=cfg["backoff_factor"],
        max_backoff_seconds=cfg["max_backoff_seconds"]
    )

    transitioned_count = 0
    new_successes = 0
    new_failures = 0
    timeout_obj = aiohttp.ClientTimeout(total=cfg["timeout_seconds"])

    batch_successes = 0
    batch_timeouts = 0

    async with aiohttp.ClientSession(timeout=timeout_obj) as session:
        for i, rg_mbid in enumerate(to_check):
            if not await rate_limiter.acquire():
                print(f"{bcolors.WARNING}🚫 Circuit breaker open, skipping remaining {len(to_check) - i} release groups{bcolors.ENDC}")
                break

            rg_data = ledger[rg_mbid]
            rg_title = rg_data.get("rg_title", "Unknown")
            artist_name = rg_data.get("artist_name", "Unknown Artist")
            prev_status = rg_data.get("status", "").lower()

            global_position = offset + i + 1
            total_to_process = offset + len(to_check)

            print(f"[{bcolors.BWHITE}{global_position}/{total_to_process}{bcolors.ENDC}] Checking {artist_name} - {rg_title} [{rg_mbid}] ...", end="", flush=True)

            try:
                status, last_code, attempts_used, response_time = await check_release_group_with_cache_warming(
                    session,
                    rg_mbid,
                    cfg["target_base_url"],
                    cfg["max_attempts_per_rg"],
                    cfg["delay_between_attempts"],
                    cfg["timeout_seconds"]
                )

                rate_limiter.release(int(last_code) if last_code.isdigit() else last_code, response_time)

                ledger[rg_mbid].update({
                    "status": status,
                    "attempts": attempts_used,
                    "last_status_code": last_code,
                    "last_checked": iso_now()
                })

                if status == "success":
                    new_successes += 1
                    batch_successes += 1
                    print(f" {bcolors.OKGREEN}SUCCESS{bcolors.ENDC} (code={last_code}, attempts={attempts_used})")
                else:
                    new_failures += 1
                    batch_timeouts += 1
                    print(f" {bcolors.FAIL}TIMEOUT{bcolors.ENDC} (code={last_code}, attempts={attempts_used})")

            except Exception as e:
                response_time = 1.0
                rate_limiter.release("EXC", response_time)

                ledger[rg_mbid].update({
                    "status": "timeout",
                    "attempts": cfg["max_attempts_per_rg"],
                    "last_status_code": f"EXC:{type(e).__name__}",
                    "last_checked": iso_now()
                })

                new_failures += 1
                batch_timeouts += 1
                print(f" {bcolors.FAIL}TIMEOUT{bcolors.ENDC} (code=EXC:{type(e).__name__}, attempts={cfg['max_attempts_per_rg']})")

            if global_position % cfg.get("batch_write_frequency", 5) == 0:
                storage.write_release_groups_ledger(ledger)

            if global_position % cfg.get("log_progress_every_n", 25) == 0:
                elapsed_time = time.time() - overall_start_time
                rgs_per_sec = global_position / max(elapsed_time, 0.1)
                remaining_rgs = total_to_process - global_position
                eta_seconds = remaining_rgs / max(rgs_per_sec, 0.01)
                etc_timestamp = datetime.now() + timedelta(seconds=eta_seconds)
                etc_str = etc_timestamp.strftime("%H:%M")
                stats = rate_limiter.get_stats()
                batch_processed = batch_successes + batch_timeouts

                print(f"Progress: {global_position}/{total_to_process} ({(global_position/total_to_process*100):.1f}%) - "
                      f"Rate: {rgs_per_sec:.1f} rgs/sec - ETC: {etc_str} - "
                      f"API: {stats.get('current_rate', 'N/A')} - Batch: {batch_successes}/{batch_processed} success")

    return transitioned_count, new_successes, new_failures


def process_release_groups_in_batches(
    to_check: List[str],
    ledger: Dict[str, Dict],
    cfg: dict,
    storage
) -> Tuple[int, int, int]:
    batch_size = cfg.get("batch_size", 25)
    total_batches = (len(to_check) + batch_size - 1) // batch_size
    total_transitioned = 0
    total_new_successes = 0
    total_new_failures = 0

    overall_start_time = time.time()
    total_processed = 0

    for batch_idx in range(0, len(to_check), batch_size):
        batch_num = batch_idx // batch_size + 1
        batch = to_check[batch_idx:batch_idx + batch_size]

        print(f"=== Release Groups Batch {bcolors.OKCYAN}{batch_num}/{total_batches} ({len(batch)} release groups){bcolors.ENDC} ===")

        batch_transitioned, batch_successes, batch_failures = asyncio.run(
            check_release_groups_concurrent_with_timing(batch, ledger, cfg, storage, overall_start_time, total_processed)
        )

        total_transitioned += batch_transitioned
        total_new_successes += batch_successes
        total_new_failures += batch_failures
        total_processed += len(batch)

        storage.write_release_groups_ledger(ledger)
        print(f"Release groups batch {batch_num} complete. Ledger updated.")

        if batch_num < total_batches and cfg.get("batch_pause_seconds", 0) > 0:
            time.sleep(cfg["batch_pause_seconds"])

    return total_transitioned, total_new_successes, total_new_failures


def process_release_groups(to_check: List[str], ledger: Dict[str, Dict], cfg: dict, storage) -> dict:
    if len(to_check) == 0:
        return {"transitioned": 0, "new_successes": 0, "new_failures": 0}

    print(f"Processing {len(to_check)} release groups with cache warming...")
    print(f"Settings: {cfg['max_attempts_per_rg']} attempts, {cfg['delay_between_attempts']}s delay, "
          f"{cfg['max_concurrent_requests']} concurrent, {cfg['rate_limit_per_second']} req/sec")

    try:
        if cfg.get("batch_size", 25) < len(to_check):
            transitioned, successes, failures = process_release_groups_in_batches(to_check, ledger, cfg, storage)
        else:
            transitioned, successes, failures = asyncio.run(
                check_release_groups_concurrent_with_timing(to_check, ledger, cfg, storage, time.time(), 0)
            )

        storage.write_release_groups_ledger(ledger)

        return {
            "transitioned": transitioned,
            "new_successes": successes,
            "new_failures": failures
        }

    except KeyboardInterrupt:
        print(f"\n{bcolors.WARNING}⚠️  Interrupted by user. Saving progress...{bcolors.ENDC}")
        storage.write_release_groups_ledger(ledger)
        return {"transitioned": 0, "new_successes": 0, "new_failures": 0}
    except Exception as e:
        print(f"{bcolors.FAIL}ERROR in release group processing: {e}{bcolors.ENDC}")
        storage.write_release_groups_ledger(ledger)
        raise
