module WorkerRecycler
  MARKER_DIRECTORY = "/api/tmp"
  @completed_groups = 0

  def self.completed_group
    @completed_groups += 1
    elapsed = Process.clock_gettime(Process::CLOCK_MONOTONIC) -
              Float(ENV.fetch("RUNNER_WORKER_STARTED_MONOTONIC"))
    rss_kib = File.read("/proc/self/status")[/^VmRSS:\s+(\d+) kB$/, 1].to_i
    allowance = Integer(ENV.fetch("RUNNER_EXEC_MEMORY_BYTES", "8589934592")) / 2048 /
                Integer(ENV.fetch("COUNT", "16"))
    reasons = []
    reasons << "groups" if @completed_groups >= Integer(ENV.fetch("RUNNER_RECYCLE_AFTER_GROUPS", "50"))
    reasons << "age" if elapsed >= Integer(ENV.fetch("RUNNER_RECYCLE_AFTER_SECONDS", "600"))
    reasons << "rss" if rss_kib >= allowance
    return if reasons.empty?

    token = ENV.fetch("RUNNER_WORKER_TOKEN")
    path = "#{MARKER_DIRECTORY}/runner-recycle-#{Process.pid}"
    File.write(path, token)
    Rails.logger.warn({event: "runner_worker_recycling", pid: Process.pid,
                       groups: @completed_groups, elapsed_seconds: elapsed,
                       rss_kib: rss_kib, allowance_kib: allowance,
                       reasons: reasons}.to_json)
    Process.kill("QUIT", Process.pid)
  end
end
