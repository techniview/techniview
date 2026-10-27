# Own worker lifetimes so container shutdown cannot leave Redis registrations behind.
require "securerandom"

count = Integer(ENV.fetch("COUNT", "4"))
abort "COUNT must be positive" unless count.positive?
if ENV["RUNNER_PERSISTENT_WORKERS"] == "1"
  abort "/api/tmp must be writable for worker recycling" unless File.writable?("/api/tmp")
end
children = []
worker_tokens = {}
stopping = false
failed = false
last_recycle = 0.0
spawn_worker = lambda do
  token = SecureRandom.hex(16)
  pid = Process.spawn({"RUNNER_WORKER_TOKEN" => token,
                       "RUNNER_WORKER_STARTED_MONOTONIC" =>
                         Process.clock_gettime(Process::CLOCK_MONOTONIC).to_s},
                      "bundle", "exec", "rake", "resque:work")
  children << pid
  worker_tokens[pid] = token
end
signal_children = lambda do
  children.each do |pid|
    begin
      Process.kill("TERM", pid)
    rescue Errno::ESRCH
      # A worker can exit between waitpid and signal delivery.
    end
  end
end
%w[TERM INT QUIT].each do |signal|
  Signal.trap(signal) do
    stopping = true
    signal_children.call
  end
end
begin
  count.times do
    break if stopping
    spawn_worker.call
  end
  if !stopping && ENV["RUNNER_GROUP_PROFILE"] == "1"
    children << Process.spawn("bundle", "exec", "ruby", "-r", "./config/environment",
                              "scripts/group_recovery.rb")
  end
  signal_children.call if stopping
  until children.empty?
    pid, status = Process.wait2
    children.delete(pid)
    token = worker_tokens.delete(pid)
    marker = "/api/tmp/runner-recycle-#{pid}"
    planned = token && ENV["RUNNER_PERSISTENT_WORKERS"] == "1" &&
              status.success? && File.file?(marker) && File.read(marker) == token
    File.delete(marker) if File.file?(marker)
    unless stopping
      if planned
        elapsed = Process.clock_gettime(Process::CLOCK_MONOTONIC) - last_recycle
        sleep([0.5 - elapsed, 0].max)
        spawn_worker.call
        last_recycle = Process.clock_gettime(Process::CLOCK_MONOTONIC)
      else
        failed = true
        stopping = true
        signal_children.call
      end
    end
  end
ensure
  unless children.empty?
    signal_children.call
    children.each do |pid|
      begin
        Process.wait(pid)
      rescue Errno::ECHILD
        # Already reaped after a signal interrupted waitpid.
      end
    end
  end
end
exit(failed ? 1 : 0)
