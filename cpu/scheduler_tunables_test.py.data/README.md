# Scheduler Tunables Test Plan - Top 4 Verifiable Tunables
# This YAML file defines test parameters for scheduler tunable validation

# Test duration in seconds
test_duration: 10

# Number of stress workers (default: 2x CPU count for overcommit)
# Set to 0 or omit to use automatic calculation
stress_workers: 0

# Individual test configurations
tests:
  baseline:
    enabled: true
    description: "Baseline test with default system tunables"
    workload_type: "mixed"
    expected_behavior: "Establishes reference metrics"
    
  low_latency:
    enabled: true
    description: "Low latency configuration - reduced time slices"
    workload_type: "cpu"
    tunables:
      base_slice_ns_factor: 0.25  # 25% of baseline
      migration_cost_ns_factor: 0.10  # 10% of baseline
    expected_behavior: "More frequent preemption, better responsiveness"
    
  high_throughput:
    enabled: true
    description: "High throughput configuration - increased time slices"
    workload_type: "context-switch"
    tunables:
      base_slice_ns_factor: 3.0  # 3x baseline
      migration_cost_ns_factor: 2.0  # 2x baseline
    expected_behavior: "Less context switching, higher throughput"
    
  migration_behavior:
    enabled: true
    description: "Migration behavior test - aggressive task migration"
    workload_type: "fork"
    tunables:
      nr_migrate_factor: 2.0  # 2x baseline, max 128
    expected_behavior: "Better load balancing with more tasks migrated"

# Tunable definitions and paths
tunables:
  base_slice_ns:
    description: "Base time slice for CFS scheduler"
    paths:
      - "/sys/kernel/debug/sched/base_slice_ns"
    unit: "nanoseconds"
    typical_range: "750000 - 6000000"  # 0.75ms - 6ms
    
  sched_migration_cost_ns:
    description: "Task migration cost threshold"
    paths:
      - "/proc/sys/kernel/sched_migration_cost_ns"
      - "/sys/kernel/debug/sched/migration_cost_ns"
    unit: "nanoseconds"
    typical_range: "50000 - 5000000"  # 50μs - 5ms
    
  sched_nr_migrate:
    description: "Number of tasks to migrate at once"
    paths:
      - "/proc/sys/kernel/sched_nr_migrate"
      - "/sys/kernel/debug/sched/nr_migrate"
    unit: "tasks"
    typical_range: "8 - 128"
    
  sched_schedstats:
    description: "Enable scheduler statistics"
    paths:
      - "/proc/sys/kernel/sched_schedstats"
    unit: "boolean"
    values: "0 (disabled) or 1 (enabled)"

# Workload types and their purpose
workloads:
  cpu:
    description: "Pure CPU-bound workload"
    stress_ng_stressor: "cpu"
    purpose: "Tests base_slice_ns impact on time slicing"
    
  context-switch:
    description: "High context switching workload"
    stress_ng_stressor: "switch"
    purpose: "Tests migration_cost_ns impact on context switches"
    
  fork:
    description: "Fork-heavy workload"
    stress_ng_stressor: "fork"
    purpose: "Tests sched_nr_migrate impact on task migration"
    
  mixed:
    description: "Mixed CPU and I/O workload"
    stress_ng_stressor: "cpu + io"
    purpose: "Overall scheduler behavior baseline"

# Expected outcomes per test
validation:
  baseline:
    - "All tunables readable and at system defaults"
    - "Workload completes successfully"
    - "Metrics collected for comparison"
    
  low_latency:
    - "Reduced time slices applied successfully"
    - "CPU workload shows impact of smaller slices"
    - "More frequent scheduling decisions"
    
  high_throughput:
    - "Increased time slices applied successfully"
    - "Context-switch workload shows reduced overhead"
    - "Fewer migrations due to higher cost threshold"
    
  migration_behavior:
    - "Increased nr_migrate applied successfully"
    - "Fork workload shows better load distribution"
    - "More tasks migrated per balancing operation"

# System requirements
requirements:
  packages:
    - stress-ng
  kernel_features:
    - CONFIG_SCHEDSTATS (optional but recommended)
    - debugfs mounted at /sys/kernel/debug
  permissions:
    - root or sudo access required
  minimum_cpus: 2
