#!/usr/bin/env bash
# Static NVIDIA/CUDA/container performance environment snapshot.
# Read-only: no benchmark, no GPU workload, no tuning, no continuous sampling.
set -u

section() { printf '\n========== %s ==========\n' "$1"; }
show_file() {
  local label="$1" path="$2"
  if [[ -r "$path" ]]; then
    printf '%s [%s]:\n' "$label" "$path"
    head -n 18 "$path" | sed 's/^/  /'
  else
    printf '%s: unavailable\n' "$label"
  fi
}
run_if_present() {
  local exe="$1"; shift
  if command -v "$exe" >/dev/null 2>&1; then
    "$exe" "$@" 2>&1 || printf '[warning] %s exited with an error\n' "$exe"
  else
    printf '%s: not installed / not visible\n' "$exe"
  fi
}

echo 'NVIDIA/CUDA static environment report (no load test)'
printf 'Report time: '; date '+%Y-%m-%d %H:%M:%S %Z'
printf 'Hostname: '; hostname 2>/dev/null || true
printf 'Kernel: '; uname -sr 2>/dev/null || true
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  printf 'OS: %s\n' "${PRETTY_NAME:-unknown}"
fi

section '1. GPU, driver, visibility'
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -L 2>&1 || true
  nvidia-smi --query-gpu=index,name,driver_version,pstate,compute_mode,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total --format=csv 2>&1 || true
else
  echo 'nvidia-smi not found'
fi
printf 'GPU device nodes:\n'
ls -l /dev/nvidia* 2>/dev/null || echo '  /dev/nvidia* not visible'

section '2. GPU clocks, power, limits'
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,clocks.current.sm,clocks.current.memory,clocks.max.sm,clocks.max.memory,power.draw,power.limit --format=csv 2>&1 || true
  echo '-- Clock limiting/event reasons (driver-dependent) --'
  nvidia-smi -q -d PERFORMANCE 2>&1 | awk '
    /GPU [0-9]+:/ {print; next}
    /Performance State|Clocks (Event|Throttle) Reasons|SW Power Cap|SW Thermal Slowdown|HW Slowdown|HW Thermal Slowdown|HW Power Brake Slowdown|Applications Clocks Setting|Display Active|Idle[[:space:]]*:/ {print}
  ' || true
  echo '-- Temperature, Power and Clock details --'
  nvidia-smi -q -d TEMPERATURE,POWER,CLOCK 2>&1 | awk '
    /GPU [0-9]+:/ {print; next}
    /^[[:space:]]{4}(Temperature|GPU Current Temp|GPU T.Limit Temp|GPU Slowdown Temp|GPU Max Operating Temp|Power Readings|Power Limit|Enforced Power Limit|Default Power Limit|Max Power Limit|Min Power Limit|Clocks|Applications Clocks|Default Applications Clocks|Max Clocks)[[:space:]]*:/ {print; next}
    /GPU Current Temp|GPU Slowdown Temp|GPU Max Operating Temp|GPU T.Limit Temp|Power Draw|Power Limit|Enforced Power Limit|SM Clock|Memory Clock|Graphics[[:space:]]*:/ {print}
  ' || true
else
  echo 'No GPU clock/power data'
fi

section '3. GPU topology, PCIe and sharing'
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,pci.bus_id,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max,mig.mode.current --format=csv 2>&1 || true
  echo '-- GPU topology --'
  nvidia-smi topo -m 2>&1 || true
  echo '-- GPU compute processes (snapshot only) --'
  nvidia-smi --query-compute-apps=gpu_uuid,pid,used_gpu_memory --format=csv 2>&1 || true
fi

section '4. CUDA toolchain and runtime'
printf 'PATH nvcc: '; command -v nvcc 2>/dev/null || echo 'not found in PATH'
if command -v nvcc >/dev/null 2>&1; then nvcc --version 2>&1 | tail -n 5; fi
for p in /usr/local/cuda /usr/local/cuda-[0-9]*; do
  [[ -e "$p" ]] || continue
  printf 'CUDA path: %s -> %s\n' "$p" "$(readlink -f "$p" 2>/dev/null || echo '?')"
  if [[ -x "$p/bin/nvcc" ]]; then
    printf '  nvcc: %s\n' "$p/bin/nvcc"
    "$p/bin/nvcc" --version 2>&1 | tail -n 4
  else
    echo '  nvcc missing here'
  fi
  for lib in "$p/lib64/libcufft.so" "$p/targets/x86_64-linux/lib/libcufft.so"; do
    [[ ! -e "$lib" ]] || printf '  cuFFT: %s\n' "$lib"
  done
done
if command -v ldconfig >/dev/null 2>&1; then
  echo '-- CUDA/cuFFT libraries in loader cache --'
  ldconfig -p 2>/dev/null | grep -E 'lib(cufft|cudart|cuda)\.so' | head -n 16 || true
fi
printf 'Selected environment variables (no secrets):\n'
for v in CUDA_VISIBLE_DEVICES NVIDIA_VISIBLE_DEVICES CUDA_HOME CUDA_PATH CUDA_DEVICE_ORDER CUDA_MODULE_LOADING CUDA_CACHE_DISABLE CUDA_CACHE_MAXSIZE CUDA_CACHE_PATH OMP_NUM_THREADS; do
  if [[ -v $v ]]; then printf '  %s=%s\n' "$v" "${!v}"; else printf '  %s=<unset>\n' "$v"; fi
done

section '5. Container / cgroup CPU allocation'
printf 'PID 1 process: '; tr '\0' ' ' </proc/1/cmdline 2>/dev/null | cut -c 1-120; printf '\n'
show_file 'Self cgroup' /proc/self/cgroup
printf 'CPU affinity: '; grep '^Cpus_allowed_list:' /proc/self/status 2>/dev/null || true
printf 'nproc (visible logical CPUs): '; nproc 2>/dev/null || echo 'unavailable'
if command -v lscpu >/dev/null 2>&1; then
  lscpu | grep -E '^(Architecture|CPU\(s\)|On-line CPU\(s\) list|Model name|Socket\(s\)|NUMA node\(s\)|NUMA node[0-9]+ CPU\(s\)|Thread\(s\) per core|CPU max MHz|CPU min MHz|Hypervisor vendor):' || true
fi
if [[ -f /sys/fs/cgroup/cgroup.controllers ]]; then
  echo 'Cgroup: v2'
  show_file 'CPU quota (quota/period usec; max = unlimited)' /sys/fs/cgroup/cpu.max
  show_file 'CPU throttling totals (since cgroup creation)' /sys/fs/cgroup/cpu.stat
  show_file 'Effective cpuset' /sys/fs/cgroup/cpuset.cpus.effective
  show_file 'Memory quota (max = unlimited)' /sys/fs/cgroup/memory.max
  show_file 'Current cgroup memory usage (bytes)' /sys/fs/cgroup/memory.current
  show_file 'Cgroup memory events' /sys/fs/cgroup/memory.events
else
  echo 'Cgroup: v1 or cgroup v2 hidden'
  show_file 'CPU quota' /sys/fs/cgroup/cpu/cpu.cfs_quota_us
  show_file 'CPU period' /sys/fs/cgroup/cpu/cpu.cfs_period_us
  show_file 'CPU throttling totals' /sys/fs/cgroup/cpu/cpu.stat
  show_file 'Cpuset' /sys/fs/cgroup/cpuset/cpuset.cpus
  show_file 'Memory quota' /sys/fs/cgroup/memory/memory.limit_in_bytes
fi

section '6. CPU frequency, memory, NUMA'
for p in /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor \
         /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq \
         /sys/devices/system/cpu/intel_pstate/no_turbo \
         /sys/devices/system/cpu/cpufreq/boost; do
  [[ ! -r "$p" ]] || printf '%s: %s\n' "$p" "$(cat "$p")"
done
run_if_present free -h
if command -v numactl >/dev/null 2>&1; then
  numactl --hardware 2>&1 | head -n 35
else
  echo 'numactl not installed (NUMA topology detail omitted)'
fi
show_file 'CPU pressure snapshot (container/host scope may vary)' /proc/pressure/cpu
show_file 'Memory pressure snapshot (container/host scope may vary)' /proc/pressure/memory

section '7. Filesystem, process limits'
printf 'Working directory: %s\n' "$PWD"
run_if_present df -hP . /tmp
if command -v findmnt >/dev/null 2>&1; then
  findmnt -T "$PWD" -o TARGET,FSTYPE,SOURCE -n 2>&1 | cut -c 1-180 || true
fi
printf 'Open files ulimit (-n): '; ulimit -n
printf 'Locked memory ulimit (-l, KiB): '; ulimit -l
printf 'Stack ulimit (-s, KiB): '; ulimit -s

section 'Interpretation'
echo '1) P-State/clocks are snapshots. Low idle clocks or an Idle clock-event reason alone are not proof of a benchmark problem.'
echo '2) CPU quotas and nr_throttled/throttled_usec can indicate possible host-side launch/synchronization contention, not GPU kernel slowdown by themselves.'
echo '3) nvidia-smi driver CUDA Version is an upper supported version, not the installed nvcc Toolkit version.'
echo '4) Container visibility of GPU power/clock controls can be incomplete; a missing field does not mean the feature is disabled.'
echo '5) This report only reads state once; it cannot establish whether clocks, power, or neighbors changed during FFT timing.'

