#!/usr/bin/env python

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: 2026 IBM
# Author: Samir <samir@linux.ibm.com>

"""
Test suite for Linux CFS scheduler tunables testing.
FOCUSED ON TOP 4 VERIFIABLE TUNABLES ONLY.

This test validates the 4 most important CFS scheduler tunables:
1. base_slice_ns - Controls the base time slice for CFS scheduler
2. sched_migration_cost_ns - Controls task migration cost threshold
3. sched_nr_migrate - Controls number of tasks to migrate at once
4. sched_schedstats - Enables scheduler statistics (required for verification)
"""

import os
import time
from avocado import Test
from avocado.utils import process, cpu, genio
from avocado.utils.software_manager.manager import SoftwareManager


class SchedulerTunablesTest(Test):
    """
    Test Linux scheduler tunables - TOP 4 VERIFIABLE TUNABLES.
    Validates scheduler behavior with different tunable configurations.

    :avocado: tags=cpu,scheduler,tunables,privileged
    """

    def setUp(self):
        """
        Setup test environment and verify scheduler support.
        """
        self.sm = SoftwareManager()

        # Install required packages
        required_packages = ['stress-ng']
        for package in required_packages:
            if not self.sm.check_installed(package):
                if not self.sm.install(package):
                    self.cancel(f"Failed to install {package}")

        # Get system information
        self.total_cpus = cpu.online_count()
        self.log.info("Total online CPUs: %d", self.total_cpus)

        # Get test parameters
        self.test_duration = int(self.params.get('test_duration', default=10))

        # Handle stress_workers: 0 means auto-calculate for 100% system stress
        yaml_workers = self.params.get('stress_workers', default=0)
        if yaml_workers == 0 or yaml_workers is None:
            # Use 8x CPU count to ensure 100% system stress and heavy
            # scheduler activity
            self.stress_workers = self.total_cpus * 8
            self.log.info(
                "Auto-calculating stress workers: %d (8x %d CPUs for "
                "100%% stress)", self.stress_workers, self.total_cpus)
        else:
            self.stress_workers = int(yaml_workers)
            self.log.info("Using configured stress workers: %d",
                          self.stress_workers)

        # Store original tunable values for restoration
        self.original_tunables = {}

        self.log.info("\n" + "=" * 70)
        self.log.info("TEST CONFIGURATION - TOP 4 TUNABLES")
        self.log.info("=" * 70)
        self.log.info("  Duration: %d seconds", self.test_duration)
        self.log.info("  Workers: %d", self.stress_workers)
        self.log.info("  CPUs: %d", self.total_cpus)
        self.log.info("=" * 70)

        # Check and save original tunables
        self._check_and_save_tunables()

    def _get_tunable_path(self, tunable_name):
        """
        Get the correct path for a tunable.
        Returns the first existing path, or None if not found.
        """
        tunable_paths = {
            'base_slice_ns': [
                '/sys/kernel/debug/sched/base_slice_ns',
            ],
            'sched_migration_cost_ns': [
                '/proc/sys/kernel/sched_migration_cost_ns',
                '/sys/kernel/debug/sched/migration_cost_ns',
            ],
            'sched_nr_migrate': [
                '/proc/sys/kernel/sched_nr_migrate',
                '/sys/kernel/debug/sched/nr_migrate',
            ],
            'sched_schedstats': [
                '/proc/sys/kernel/sched_schedstats',
            ],
        }

        paths = tunable_paths.get(tunable_name, [])
        for path in paths:
            if os.path.exists(path):
                return path
        return None

    def _check_and_save_tunables(self):
        """
        Check availability and save original values of top 4 tunables.
        """
        self.log.info("\n--- Checking Top 4 Scheduler Tunables ---")

        tunables = [
            'base_slice_ns',
            'sched_migration_cost_ns',
            'sched_nr_migrate',
            'sched_schedstats',
        ]

        for tunable_name in tunables:
            tunable_path = self._get_tunable_path(tunable_name)
            if tunable_path:
                try:
                    value = genio.read_file(tunable_path).strip()
                    self.original_tunables[tunable_path] = value
                    self.log.info("  ✓ %s = %s", tunable_name, value)
                except Exception as e:
                    self.log.warning(
                        "  ⚠ Failed to read %s: %s", tunable_name, str(e))
            else:
                self.log.warning("  ✗ %s NOT FOUND", tunable_name)

        self.log.info("=" * 70)

    def _set_tunable(self, tunable_name, value):
        """
        Set a scheduler tunable value.
        """
        tunable_path = self._get_tunable_path(tunable_name)
        if not tunable_path:
            self.log.warning("Tunable %s not found", tunable_name)
            return False

        try:
            genio.write_file(tunable_path, str(value))
            self.log.info("Set %s = %s", tunable_name, value)
            return True
        except Exception as e:
            self.log.error("Failed to set %s: %s", tunable_name, str(e))
            return False

    def _get_tunable(self, tunable_name):
        """
        Get current value of a scheduler tunable.
        """
        tunable_path = self._get_tunable_path(tunable_name)
        if not tunable_path:
            return None

        try:
            return genio.read_file(tunable_path).strip()
        except Exception as e:
            self.log.error("Failed to read %s: %s", tunable_name, str(e))
            return None

    def _restore_tunables(self):
        """
        Restore original tunable values.
        """
        self.log.info("\n--- Restoring Original Tunables ---")
        for tunable_path, value in self.original_tunables.items():
            try:
                genio.write_file(tunable_path, value)
                self.log.info("  Restored %s = %s", tunable_path, value)
            except Exception as e:
                self.log.warning("  Failed to restore %s: %s",
                                 tunable_path, str(e))

    def _run_workload_single(self, duration=None, workload_type='cpu'):
        """
        Run a single iteration of workload with perf stat.
        Internal method - use _run_workload() for averaged results.
        """
        if duration is None:
            duration = self.test_duration

        # Build stress-ng command based on workload type
        if workload_type == 'cpu':
            stress_cmd = (
                f"stress-ng --cpu {self.stress_workers} "
                f"--timeout {duration}s")
            self.log.info("Running CPU-bound workload (tests base_slice_ns)")

        elif workload_type == 'context-switch':
            workers = min(self.stress_workers, self.total_cpus * 4)
            stress_cmd = f"stress-ng --switch {workers} --timeout {duration}s"
            self.log.info(
                "Running context-switch workload (tests migration_cost_ns)")

        elif workload_type == 'fork':
            workers = min(self.stress_workers // 2, 64)
            stress_cmd = f"stress-ng --fork {workers} --timeout {duration}s"
            self.log.info("Running fork workload (tests sched_nr_migrate)")

        elif workload_type == 'mixed':
            cpu_workers = self.stress_workers // 2
            io_workers = self.stress_workers // 4
            stress_cmd = (
                f"stress-ng --cpu {cpu_workers} --io {io_workers} "
                f"--timeout {duration}s")
            self.log.info("Running mixed CPU+I/O workload")

        else:
            stress_cmd = (
                f"stress-ng --cpu {self.stress_workers} "
                f"--timeout {duration}s")

        # Run with perf stat - same metrics as your example
        perf_cmd = (
            f"perf stat -e context-switches,cpu-migrations,page-faults,"
            f"task-clock,branch-misses,branches,cpu-cycles,instructions "
            f"{stress_cmd}")
        self.log.info("Command: %s", perf_cmd)

        try:
            result = process.run(perf_cmd, shell=True, ignore_status=True)

            # perf stat output goes to stderr
            perf_output = result.stderr.decode() if result.stderr else ""

            # Parse metrics from perf output
            metrics = {
                'context_switches': 0,
                'cs_per_second': 0.0,
                'cpu_migrations': 0,
                'migrations_per_second': 0.0,
                'page_faults': 0,
                'task_clock_ms': 0.0,
                'cpus_utilized': 0.0,
                'branch_misses': 0,
                'branch_miss_rate': 0.0,
                'branches': 0,
                'cpu_cycles': 0,
                'instructions': 0,
                'insn_per_cycle': 0.0,
                'time_elapsed': 0.0
            }

            # Parse perf stat output line by line
            for line in perf_output.split('\n'):
                line = line.strip()

                if 'context-switches' in line:
                    parts = line.split()
                    metrics['context_switches'] = int(
                        parts[0].replace(',', ''))
                    # Extract cs/sec if present
                    for i, part in enumerate(parts):
                        if 'cs/sec' in part and i > 0:
                            metrics['cs_per_second'] = float(parts[i-1])

                elif 'cpu-migrations' in line:
                    parts = line.split()
                    metrics['cpu_migrations'] = int(parts[0].replace(',', ''))
                    # Extract migrations/sec if present
                    for i, part in enumerate(parts):
                        if 'migrations/sec' in part and i > 0:
                            metrics['migrations_per_second'] = float(
                                parts[i-1])

                elif 'page-faults' in line:
                    parts = line.split()
                    metrics['page_faults'] = int(parts[0].replace(',', ''))

                elif 'task-clock' in line:
                    parts = line.split()
                    metrics['task_clock_ms'] = float(parts[0].replace(',', ''))
                    # Extract CPUs utilized
                    for i, part in enumerate(parts):
                        if 'CPUs' in part and i > 0:
                            metrics['cpus_utilized'] = float(parts[i-1])

                elif 'branch-misses' in line and 'branches' not in line:
                    parts = line.split()
                    metrics['branch_misses'] = int(parts[0].replace(',', ''))
                    # Extract miss rate
                    for i, part in enumerate(parts):
                        if '%' in part:
                            metrics['branch_miss_rate'] = float(
                                part.replace('%', ''))

                elif (line.startswith('branches') or
                      ('branches' in line and 'branch-misses' not in line)):
                    parts = line.split()
                    if parts[0].replace(',', '').isdigit():
                        metrics['branches'] = int(parts[0].replace(',', ''))

                elif 'cpu-cycles' in line:
                    parts = line.split()
                    metrics['cpu_cycles'] = int(parts[0].replace(',', ''))

                elif 'instructions' in line:
                    parts = line.split()
                    metrics['instructions'] = int(parts[0].replace(',', ''))
                    # Extract IPC
                    for i, part in enumerate(parts):
                        if 'instructions' in part and i > 1:
                            try:
                                metrics['insn_per_cycle'] = float(parts[i-1])
                            except (ValueError, IndexError):
                                pass

                elif 'seconds time elapsed' in line:
                    parts = line.split()
                    metrics['time_elapsed'] = float(parts[0])

            # Log the key metrics
            self.log.info("\n" + "=" * 70)
            self.log.info("SCHEDULER METRICS (via perf stat)")
            self.log.info("=" * 70)
            self.log.info(
                "Context switches: %d (%.1f cs/sec)",
                metrics['context_switches'], metrics['cs_per_second'])
            self.log.info(
                "CPU migrations: %d (%.1f migrations/sec)",
                metrics['cpu_migrations'],
                metrics['migrations_per_second'])
            self.log.info("Page faults: %d", metrics['page_faults'])
            self.log.info("Task clock: %.2f ms (%.1f CPUs utilized)",
                          metrics['task_clock_ms'], metrics['cpus_utilized'])
            self.log.info("Instructions per cycle: %.2f",
                          metrics['insn_per_cycle'])
            self.log.info("Time elapsed: %.2f seconds",
                          metrics['time_elapsed'])

            # Calculate derived metrics
            if metrics['context_switches'] > 0:
                migrations_per_1k_cs = (
                    metrics['cpu_migrations'] * 1000.0 /
                    metrics['context_switches'])
                self.log.info("\nDerived Metrics:")
                self.log.info(
                    "  Migrations per 1000 context switches: %.2f",
                    migrations_per_1k_cs)

            self.log.info("=" * 70)

            return {
                'success': result.exit_status == 0,
                'metrics': metrics,
                'raw_output': perf_output
            }

        except Exception as e:
            self.log.error("Workload with perf failed: %s", str(e))
            return {
                'success': False,
                'metrics': {},
                'raw_output': str(e)
            }

    def _run_workload(self, duration=None, workload_type='cpu', iterations=10):
        """
        Run workload multiple times and return AVERAGE metrics.

        This reduces noise and provides more reliable measurements.
        Default: 10 iterations

        Returns dict with:
        - success: bool
        - metrics: dict with averaged values
        - all_runs: list of individual run metrics
        - std_dev: standard deviation for key metrics
        """
        if duration is None:
            duration = self.test_duration

        self.log.info(
            "\n--- Running %d iterations for reliable metrics ---", iterations)

        all_runs = []
        successful_runs = 0

        for i in range(iterations):
            self.log.info("Iteration %d/%d...", i + 1, iterations)
            result = self._run_workload_single(duration, workload_type)

            if result['success']:
                all_runs.append(result['metrics'])
                successful_runs += 1
            else:
                self.log.warning("Iteration %d failed", i + 1)

        if successful_runs == 0:
            return {
                'success': False,
                'metrics': {},
                'all_runs': [],
                'std_dev': {}
            }

        # Calculate averages
        avg_metrics = {}
        std_dev = {}

        metric_keys = all_runs[0].keys() if all_runs else []

        for key in metric_keys:
            values = [run[key] for run in all_runs if key in run]
            if values:
                avg_metrics[key] = sum(values) / len(values)

                # Calculate standard deviation for key metrics
                if key in ['context_switches', 'cpu_migrations',
                           'page_faults']:
                    mean = avg_metrics[key]
                    variance = sum(
                        (x - mean) ** 2 for x in values) / len(values)
                    std_dev[key] = variance ** 0.5

        self.log.info("\n" + "=" * 70)
        self.log.info("AVERAGED METRICS (%d successful runs)", successful_runs)
        self.log.info("=" * 70)
        self.log.info("Context switches: %.0f (±%.0f)",
                      avg_metrics.get('context_switches', 0),
                      std_dev.get('context_switches', 0))
        self.log.info("CPU migrations: %.0f (±%.0f)",
                      avg_metrics.get('cpu_migrations', 0),
                      std_dev.get('cpu_migrations', 0))
        self.log.info("Page faults: %.0f (±%.0f)",
                      avg_metrics.get('page_faults', 0),
                      std_dev.get('page_faults', 0))
        self.log.info("Task clock: %.2f ms",
                      avg_metrics.get('task_clock_ms', 0))
        self.log.info("Instructions per cycle: %.2f",
                      avg_metrics.get('insn_per_cycle', 0))

        if avg_metrics.get('context_switches', 0) > 0:
            migrations_per_1k = (
                avg_metrics.get('cpu_migrations', 0) * 1000.0 /
                avg_metrics['context_switches'])
            self.log.info(
                "Migrations per 1000 context switches: %.2f",
                migrations_per_1k)

        self.log.info("=" * 70)

        return {
            'success': True,
            'metrics': avg_metrics,
            'all_runs': all_runs,
            'std_dev': std_dev,
            'successful_runs': successful_runs,
            'total_runs': iterations
        }

    def test_01_baseline(self):
        """
        Test 1: Verify scheduler behavior with default tunables.
        Tests that scheduler works correctly with system default values.
        """
        self.log.info("\n" + "=" * 70)
        self.log.info("TEST 1: DEFAULT TUNABLES Verification")
        self.log.info("=" * 70)

        # Display current values
        self.log.info("\nCurrent tunable values:")
        baseline_base_slice = self._get_tunable('base_slice_ns')
        baseline_migration_cost = self._get_tunable('sched_migration_cost_ns')
        baseline_nr_migrate = self._get_tunable('sched_nr_migrate')
        baseline_schedstats = self._get_tunable('sched_schedstats')

        self.log.info("  base_slice_ns = %s", baseline_base_slice)
        self.log.info("  sched_migration_cost_ns = %s",
                      baseline_migration_cost)
        self.log.info("  sched_nr_migrate = %s", baseline_nr_migrate)
        self.log.info("  sched_schedstats = %s", baseline_schedstats)

        # Run workload with default tunables
        self.log.info("\nRunning workload with DEFAULT tunables...")
        result = self._run_workload(workload_type='mixed')

        if result['success']:
            metrics = result['metrics']

            # Validate that metrics are reasonable
            self.log.info("\n--- VALIDATION: Default Tunable Behavior ---")
            self.log.info("Context switches: %d",
                          metrics.get('context_switches', 0))
            self.log.info("CPU migrations: %d",
                          metrics.get('cpu_migrations', 0))

            # Basic sanity checks
            if metrics.get('context_switches', 0) > 0:
                self.log.info(
                    "✓ Context switches detected (scheduler is working)")
            else:
                self.log.warning("⚠ No context switches detected")

            if metrics.get('cpu_migrations', 0) > 0:
                self.log.info(
                    "✓ CPU migrations detected (load balancing is working)")
            else:
                self.log.warning("⚠ No CPU migrations detected")

            # Store baseline for comparison in other tests
            self.baseline_metrics = metrics
            self.log.info("\n✓ Default tunables test completed successfully")
            self.log.info(
                "✓ Baseline metrics stored for comparison in other tests")
        else:
            self.fail("Baseline test failed")

    def test_02_low_latency(self):
        """
        Test 2: Low latency configuration (reduced base_slice_ns and
        migration_cost_ns).
        VALIDATION: Collect baseline BEFORE changing, then AFTER changing,
        and compare.
        """
        self.log.info("\n" + "=" * 70)
        self.log.info("TEST 2: LOW LATENCY Configuration")
        self.log.info("=" * 70)

        # Get baseline tunable values
        baseline_base_slice = self._get_tunable('base_slice_ns')
        baseline_migration_cost = self._get_tunable('sched_migration_cost_ns')

        if baseline_base_slice and baseline_migration_cost:
            # STEP 1: Run workload with DEFAULT tunables to get baseline
            # metrics
            self.log.info("\n--- STEP 1: Baseline (Default Tunables) ---")
            self.log.info("Current tunables:")
            self.log.info(
                "  base_slice_ns: %d (%.2f ms)",
                int(baseline_base_slice),
                int(baseline_base_slice) / 1_000_000)
            self.log.info(
                "  migration_cost_ns: %d (%.2f ms)",
                int(baseline_migration_cost),
                int(baseline_migration_cost) / 1_000_000)

            self.log.info("\nRunning workload with DEFAULT tunables...")
            baseline_result = self._run_workload(workload_type='cpu')

            if not baseline_result['success']:
                self.fail("Baseline workload failed")

            # STEP 2: Change tunables to low latency values
            self.log.info("\n--- STEP 2: Low Latency (Modified Tunables) ---")
            low_base_slice = max(750000, int(baseline_base_slice) // 4)
            low_migration_cost = max(50000, int(baseline_migration_cost) // 10)

            self.log.info("Setting low latency tunables:")
            self.log.info(
                "  base_slice_ns: %d -> %d (%.2f ms -> %.2f ms)",
                int(baseline_base_slice), low_base_slice,
                int(baseline_base_slice) / 1_000_000,
                low_base_slice / 1_000_000)
            self.log.info(
                "  migration_cost_ns: %d -> %d (%.2f ms -> %.2f ms)",
                int(baseline_migration_cost), low_migration_cost,
                int(baseline_migration_cost) / 1_000_000,
                low_migration_cost / 1_000_000)

            self._set_tunable('base_slice_ns', low_base_slice)
            self._set_tunable('sched_migration_cost_ns', low_migration_cost)
            time.sleep(2)  # Allow tunables to take effect

            # STEP 3: Run same workload with MODIFIED tunables
            self.log.info("\nRunning workload with LOW LATENCY tunables...")
            test_result = self._run_workload(workload_type='cpu')

            # STEP 4: Compare metrics
            if test_result['success']:
                self.log.info("\n" + "=" * 70)
                self.log.info("VALIDATION: Comparing Baseline vs Low Latency")
                self.log.info("=" * 70)

                baseline_cs = baseline_result['metrics'].get(
                    'context_switches', 0)
                test_cs = test_result['metrics'].get('context_switches', 0)
                baseline_mig = baseline_result['metrics'].get(
                    'cpu_migrations', 0)
                test_mig = test_result['metrics'].get('cpu_migrations', 0)

                self.log.info("\nContext Switches:")
                self.log.info("  Baseline (default): %d", baseline_cs)
                self.log.info("  Low Latency: %d", test_cs)
                if baseline_cs > 0:
                    cs_change_pct = (
                        (test_cs - baseline_cs) / baseline_cs) * 100
                    self.log.info("  Change: %+.1f%%", cs_change_pct)
                    if cs_change_pct > 0:
                        self.log.info(
                            "  ✓ EXPECTED: More context switches with "
                            "smaller time slices")
                    else:
                        self.log.warning(
                            "  ⚠ UNEXPECTED: Fewer context switches")

                self.log.info("\nCPU Migrations:")
                self.log.info("  Baseline (default): %d", baseline_mig)
                self.log.info("  Low Latency: %d", test_mig)
                if baseline_mig > 0:
                    mig_change_pct = (
                        (test_mig - baseline_mig) / baseline_mig) * 100
                    self.log.info("  Change: %+.1f%%", mig_change_pct)

                self.log.info("=" * 70)

            # Restore tunables
            self._restore_tunables()

            if test_result['success']:
                self.log.info("\n✓ Low latency test completed successfully")
            else:
                self.fail("Low latency test failed")
        else:
            self.cancel("Required tunables not available")

    def test_03_high_throughput(self):
        """
        Test 3: High throughput configuration (increased base_slice_ns
        and migration_cost_ns).
        Uses context-switch workload to test migration cost impact.
        """
        self.log.info("\n" + "=" * 70)
        self.log.info("TEST 3: HIGH THROUGHPUT Configuration")
        self.log.info("=" * 70)

        # Get baseline values
        baseline_base_slice = self._get_tunable('base_slice_ns')
        baseline_migration_cost = self._get_tunable('sched_migration_cost_ns')

        if baseline_base_slice and baseline_migration_cost:
            # Set high throughput values (3x baseline)
            high_base_slice = int(baseline_base_slice) * 3
            high_migration_cost = int(baseline_migration_cost) * 2

            self.log.info("\nSetting high throughput tunables:")
            self.log.info(
                "  base_slice_ns: %d -> %d (%.2f ms -> %.2f ms)",
                int(baseline_base_slice), high_base_slice,
                int(baseline_base_slice) / 1_000_000,
                high_base_slice / 1_000_000)
            self.log.info(
                "  migration_cost_ns: %d -> %d (%.2f ms -> %.2f ms)",
                int(baseline_migration_cost), high_migration_cost,
                int(baseline_migration_cost) / 1_000_000,
                high_migration_cost / 1_000_000)

            self._set_tunable('base_slice_ns', high_base_slice)
            self._set_tunable('sched_migration_cost_ns', high_migration_cost)

            time.sleep(2)  # Allow tunables to take effect

            # Run context-switch workload - best for testing
            # migration_cost_ns impact
            self.log.info("\nRunning high throughput workload...")
            result = self._run_workload(workload_type='context-switch')

            # Restore tunables
            self._restore_tunables()

            if result:
                self.log.info(
                    "✓ High throughput test completed successfully")
            else:
                self.fail("High throughput test failed")
        else:
            self.cancel(
                "Required tunables not available for high throughput test")

    def test_04_migration_behavior(self):
        """
        Test 4: Test migration behavior with different sched_nr_migrate values.
        VALIDATION: Higher nr_migrate may show different migration patterns.
        """
        self.log.info("\n" + "=" * 70)
        self.log.info("TEST 4: MIGRATION BEHAVIOR Test")
        self.log.info("=" * 70)

        baseline_nr_migrate = self._get_tunable('sched_nr_migrate')

        if baseline_nr_migrate:
            # Test with aggressive migration (2x baseline)
            aggressive_nr_migrate = min(128, int(baseline_nr_migrate) * 2)

            self.log.info("\nSetting aggressive migration:")
            self.log.info(
                "  sched_nr_migrate: %d -> %d tasks per migration",
                int(baseline_nr_migrate), aggressive_nr_migrate)
            self.log.info(
                "  Higher value = more tasks migrated at once = "
                "better load balancing")

            self._set_tunable('sched_nr_migrate', aggressive_nr_migrate)

            time.sleep(2)  # Allow tunable to take effect

            # Run fork workload - best for testing sched_nr_migrate impact
            self.log.info("\nRunning migration test workload...")
            result = self._run_workload(workload_type='fork')

            # Validate impact
            if result['success'] and hasattr(self, 'baseline_metrics'):
                self.log.info("\n--- VALIDATION: Tunable Impact ---")
                baseline_mig = self.baseline_metrics.get('cpu_migrations', 0)
                test_mig = result['metrics'].get('cpu_migrations', 0)

                self.log.info(
                    "CPU migrations: %d (baseline) -> %d "
                    "(aggressive nr_migrate)", baseline_mig, test_mig)
                self.log.info(
                    "sched_nr_migrate controls how many tasks are "
                    "migrated per load balancing operation")
                self.log.info(
                    "Higher value can improve load distribution but "
                    "may increase overhead")

                if baseline_mig > 0:
                    mig_change_pct = (
                        (test_mig - baseline_mig) / baseline_mig) * 100
                    self.log.info("Change: %+.1f%%", mig_change_pct)

            # Restore tunables
            self._restore_tunables()

            if result['success']:
                self.log.info(
                    "✓ Migration behavior test completed successfully")
            else:
                self.fail("Migration behavior test failed")
        else:
            self.cancel("sched_nr_migrate tunable not available")

    def tearDown(self):
        """
        Cleanup: Restore original tunables.
        """
        self._restore_tunables()
        self.log.info("\n" + "=" * 70)
        self.log.info("TEST SUITE COMPLETED")
        self.log.info("=" * 70)
