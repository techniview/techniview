require "json"
require "open3"
require "timeout"

# Keeps case identities, answers, persistence, and callbacks outside student Python.
class SharedGroupExecution
  MAX_EVENT_BYTES = 8 * 1024 * 1024

  def self.perform(group_id)
    new(group_id).perform
  end

  def initialize(group_id)
    @group_id = group_id
    @callback_executor = IsolateJob.new
    @cases = SubmissionGroup.find(group_id).group_cases.includes(:submission).order(:position).to_a
    @last_frame = nil
    @completed_frames = 0
    @started_index = nil
    @cleanup_failed = false
  end

  def perform
    claim = claim_group
    return if claim == :busy || claim == :finished
    if claim.is_a?(Array)
      @attempt = claim.last
      finish_group("unknown")
      return
    end
    @attempt = claim

    termination = "unknown"
    begin
      termination = run_coordinator
    rescue Timeout::Error
      termination = "timeout"
    rescue StandardError => error
      Rails.logger.error({event: "shared_group_coordinator_failed", group_id: @group_id,
                          error: error.class.name}.to_json)
    end
    finish_group(termination)
    WorkerRecycler.completed_group if ENV["RUNNER_PERSISTENT_WORKERS"] == "1"
  end

  private

  def worker_start_ticks(pid)
    File.read("/proc/#{pid}/stat").split(") ", 2).last.split.fetch(19).to_i
  rescue Errno::ENOENT, Errno::ESRCH, IndexError
    nil
  end

  def previous_worker_alive?(group)
    return true if group.shared_execution_host != ENV["HOSTNAME"]
    return false unless group.shared_worker_pid && group.shared_worker_started_ticks
    worker_start_ticks(group.shared_worker_pid) == group.shared_worker_started_ticks
  end

  def group_wall_budget(group)
    group.group_cases.includes(:submission).sum { |item| item.submission.wall_time_limit.to_f }
  end

  def claim_group
    SubmissionGroup.transaction do
      group = SubmissionGroup.lock.find(@group_id)
      next :finished if group.state == "complete"
      if group.shared_started_at
        elapsed = Time.now.utc - group.shared_started_at
        next :busy if previous_worker_alive?(group) &&
                      elapsed < group_wall_budget(group) + 30
        token = SecureRandom.uuid
        group.update!(shared_attempt_token: token)
        next [:stale, token]
      end
      token = SecureRandom.uuid
      group.update!(state: "running", shared_attempt_token: token,
                    shared_started_at: Time.now.utc,
                    shared_execution_host: ENV["HOSTNAME"],
                    shared_worker_pid: Process.pid,
                    shared_worker_started_ticks: worker_start_ticks(Process.pid))
      token
    end
  end

  def coordinator_config
    limits = @cases.map(&:submission)
    {
      engine: ENV["RUNNER_ENGINE"] == "go-judge" ? "go-judge" : "isolate",
      script: SubmissionGroup.find(@group_id).shared_script,
      cases: @cases.map do |item|
        {input: item.shared_input,
         output_limit_bytes: [item.submission.max_file_size * 1024, 4 * 1024 * 1024].min}
      end,
      limits: {
        cpu: limits.sum { |child| child.cpu_time_limit.to_f },
        cpu_extra: limits.sum { |child| child.cpu_extra_time.to_f },
        wall: limits.sum { |child| child.wall_time_limit.to_f },
        memory_kb: limits.map(&:memory_limit).max,
        stack_kb: limits.map(&:stack_limit).max,
        processes: limits.map(&:max_processes_and_or_threads).max,
        file_kb: limits.map(&:max_file_size).max
      }
    }
  end

  def run_coordinator
    config = coordinator_config
    stdin = stdout = stderr = wait_thread = nil
    finished = nil
    Open3.popen3(IsolateJob::PYTHON, "-I", "-B",
                 "/api/scripts/shared_python_coordinator.py", pgroup: true) do |input, output, errors, process|
      stdin, stdout, stderr, wait_thread = input, output, errors, process
      stderr_thread = Thread.new { errors.each_line { |_line| nil } }
      begin
        Timeout.timeout(config.fetch(:limits).fetch(:wall) + 15) do
          stdin.write(JSON.generate(config) + "\n")
          stdin.flush
          while line = stdout.gets(MAX_EVENT_BYTES)
            event = JSON.parse(line)
            case event.fetch("type")
            when "stage"
              log_stage(event)
            when "start"
              start_case(event.fetch("index"))
              stdin.write("ack\n")
              stdin.flush
            when "case"
              receive_case(event.fetch("frame"))
              stdin.write("ack\n")
              stdin.flush
            when "cleanup_error"
              @cleanup_failed = true
            when "coordinator_error"
              Rails.logger.warn({event: "shared_group_protocol_error",
                                 group_id: @group_id,
                                 error_class: event["error_class"]}.to_json)
            when "finish"
              raise "duplicate shared group finish" if finished
              finished = event
            else
              raise "unknown shared group event"
            end
          end
          stdin.close
          wait_thread.join(5)
          raise "shared coordinator did not exit" if wait_thread.alive?
          raise "shared coordinator exited without result" unless finished
          raise "shared coordinator result count mismatch" unless
            finished.fetch("completed_cases") == @completed_frames
          raise "shared coordinator failed" unless wait_thread.value.success?
        end
      ensure
        if wait_thread.alive?
          Process.kill("KILL", -wait_thread.pid) rescue nil
          wait_thread.join(5)
        end
        stderr_thread.join(1)
      end
    end
    @cleanup_failed ? "unknown" : finished.fetch("termination")
  end

  def log_stage(event)
    seconds = Float(event.fetch("seconds"))
    raise "invalid shared group stage" unless seconds.finite? && seconds >= 0
    Rails.logger.warn({event: "runner_stage", group_id: @group_id,
                       stage: event.fetch("stage"), seconds: seconds,
                       at: Time.now.utc.iso8601(6)}.to_json)
  end

  def start_case(index)
    raise "unexpected shared group case start" unless index == @completed_frames &&
                                                    @started_index.nil?
    now = Time.now.utc
    SubmissionGroup.transaction do
      group = SubmissionGroup.lock.find(@group_id)
      raise "shared group attempt changed" unless group.shared_attempt_token == @attempt
      item = group.group_cases.order(:position).offset(index).first!
      raise "shared group case already started" unless item.state == "queued"
      item.update!(state: "running", attempt_token: @attempt, started_at: now)
      item.submission.update!(status: Status.process, started_at: now,
                              execution_host: ENV["HOSTNAME"])
    end
    @started_index = index
  end

  def receive_case(frame)
    index = frame.fetch("index")
    raise "unexpected shared group case result" unless index == @started_index
    result = result_from_frame(@cases.fetch(index).submission, frame)
    if index == @cases.size - 1
      @last_frame = frame
    else
      save_case(index, result)
      deliver_inline(@cases.fetch(index).submission)
    end
    @completed_frames += 1
    @started_index = nil
  end

  def result_from_frame(child, frame)
    stdout = frame.fetch("stdout")
    stderr = frame.fetch("stderr")
    raise "invalid shared case output" unless stdout.is_a?(String) && stderr.is_a?(String)
    status = if frame.fetch("output_exceeded")
               Status.sigxfsz
             elsif frame["exception"]
               Status.nzec
             elsif @callback_executor.send(:normalized, child.expected_output) ==
                   @callback_executor.send(:normalized, stdout)
               Status.ac
             else
               Status.wa
             end
    {status: status, stdout: stdout.presence, stderr: stderr.presence}
  end

  def save_case(index, result)
    measure("result_persistence", index) do
      SubmissionGroup.transaction do
        group = SubmissionGroup.lock.find(@group_id)
        raise "shared group attempt changed" unless group.shared_attempt_token == @attempt
        item = group.group_cases.order(:position).offset(index).first!
        raise "shared group case not running" unless item.state == "running" &&
                                                     item.attempt_token == @attempt
        persist_case(item, result, "complete")
      end
    end
  end

  def persist_case(item, result, state)
    now = Time.now.utc
    child = item.submission
    child.assign_attributes(result)
    child.finished_at = now
    child.save!
    item.update!(state: state, finished_at: now)
    if ENV["RUNNER_CALLBACK_OUTBOX"] == "1" && child.callback_url.present?
      CallbackDelivery.create!(submission_id: child.id, url: child.callback_url,
                               payload: @callback_executor.send(:callback_payload, child),
                               next_attempt_at: now)
    end
  end

  def fatal_result(termination, frame = nil)
    status = case termination
             when "timeout" then Status.tle
             when "memory" then Status.other
             when "output" then Status.sigxfsz
             when "fatal" then Status.nzec
             else Status.boxerr
             end
    {status: status, message: "runner_shared_#{termination}",
     stdout: frame && frame["stdout"], stderr: frame && frame["stderr"]}
  end

  def finish_group(termination)
    termination = "unknown" unless %w[complete timeout memory output fatal unknown].include?(termination)
    termination = "unknown" if termination == "complete" && @completed_frames != @cases.size
    callbacks = []
    SubmissionGroup.transaction do
      group = SubmissionGroup.lock.find(@group_id)
      return if group.state == "complete"
      return unless group.shared_attempt_token == @attempt
      current = termination == "complete" ? @cases.size - 1 :
                [@completed_frames, @cases.size - 1].min
      last_output = @completed_frames == @cases.size ? @last_frame : nil
      group.group_cases.includes(:submission).order(:position).each_with_index do |item, index|
        next if item.state == "complete"
        if index == current
          result = termination == "complete" ?
                   result_from_frame(item.submission, @last_frame) :
                   fatal_result(termination, last_output)
          persist_case(item, result, "complete")
        else
          persist_case(item,
                       {status: Status.boxerr,
                        message: "runner_shared_#{termination}_unrun"},
                       "unrun")
        end
        callbacks << item.submission
      end
      group.update!(state: "complete", shared_termination: termination,
                    shared_finished_at: Time.now.utc, shared_attempt_token: nil)
    end
    callbacks.each { |child| deliver_inline(child) }
  end

  def deliver_inline(child)
    return if ENV["RUNNER_CALLBACK_OUTBOX"] == "1"
    measure("callback_delivery", child.id) do
      @callback_executor.send(:call_callback, child.reload)
    end
  rescue StandardError => error
    Rails.logger.warn({event: "shared_group_callback_failed", group_id: @group_id,
                       error: error.class.name}.to_json)
  end

  def measure(stage, case_id)
    started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    yield
  ensure
    if ENV["RUNNER_BENCHMARK_TIMINGS"] == "1"
      Rails.logger.warn({event: "runner_stage", group_id: @group_id, case_id: case_id,
                         stage: stage,
                         seconds: Process.clock_gettime(Process::CLOCK_MONOTONIC) - started,
                         at: Time.now.utc.iso8601(6)}.to_json)
    end
  end
end
