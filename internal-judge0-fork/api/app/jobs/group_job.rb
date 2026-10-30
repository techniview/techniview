class GroupJob < ApplicationJob
  queue_as ENV.fetch("JUDGE0_VERSION")

  def perform(group_id, queue_clock = nil)
    if ENV["RUNNER_BENCHMARK_TIMINGS"] == "1" && queue_clock &&
       queue_clock["boot_id"] == File.read("/proc/sys/kernel/random/boot_id").strip
      Rails.logger.warn({event: "runner_stage", group_id: group_id,
                         stage: "runner_queue_wait",
                         seconds: Process.clock_gettime(Process::CLOCK_MONOTONIC) - queue_clock.fetch("enqueued"),
                         at: Time.now.utc.iso8601(6)}.to_json)
    end
    executor = ExecutionJob.new
    group = SubmissionGroup.find(group_id)
    group.group_cases.order(:position).pluck(:id).each do |case_id|
      case_row, attempt = claim_case(group_id, case_id)
      next if attempt == :finished
      return if attempt == :busy
      if attempt == :unknown
        deliver_inline(case_row.submission, executor)
        next
      end

      started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
      executor.instance_variable_set(:@benchmark_submission_id, case_row.submission_id)
      begin
        result = executor.send(:execute, case_row.submission)
      rescue StandardError => error
        Rails.logger.error({event: "group_execution_error", group_id: group_id,
                            case_id: case_id, error: error.class.name}.to_json)
        result = {status: Status.boxerr, message: executor.send(:execution_error_message, error)}
      end
      saved = measure("result_persistence", group_id, case_id) do
        save_result(group_id, case_id, attempt, result, executor)
      end
      next unless saved

      Rails.logger.warn({event: "runner_stage", group_id: group_id, case_id: case_id,
                         stage: "group_case_total",
                         seconds: Process.clock_gettime(Process::CLOCK_MONOTONIC) - started,
                         at: Time.now.utc.iso8601(6)}.to_json) if ENV["RUNNER_BENCHMARK_TIMINGS"] == "1"
      measure("callback_delivery", group_id, case_id) do
        deliver_inline(case_row.submission, executor)
      end
    end
    completed_now = false
    SubmissionGroup.transaction do
      locked = SubmissionGroup.lock.find(group_id)
      if locked.state != "complete" &&
         locked.group_cases.where.not(state: ["complete", "unknown"]).none?
        locked.update!(state: "complete")
        completed_now = true
      end
    end
    WorkerRecycler.completed_group if completed_now
  end

  private

  def claim_case(group_id, case_id)
    SubmissionGroup.transaction do
      group = SubmissionGroup.lock.find(group_id)
      item = group.group_cases.includes(:submission).find(case_id)
      next [nil, :finished] if %w[complete unknown].include?(item.state)
      if item.state == "running"
        if item.started_at.nil? || item.started_at >
           Time.now.utc - item.submission.wall_time_limit.seconds - 30.seconds
          next [nil, :busy]
        end
        mark_unknown(item)
        next [item, :unknown]
      end
      token = SecureRandom.uuid
      now = Time.now.utc
      item.update!(state: "running", attempt_token: token, started_at: now)
      item.submission.update!(status: Status.process, started_at: now,
                              execution_host: ENV["HOSTNAME"])
      group.update!(state: "running") if group.state == "queued"
      [item, token]
    end
  end

  def mark_unknown(item)
    now = Time.now.utc
    item.submission.update!(status: Status.boxerr, message: "runner_outcome_unknown", finished_at: now)
    item.update!(state: "unknown", finished_at: now, attempt_token: nil)
  end

  def save_result(group_id, case_id, attempt, result, executor)
    SubmissionGroup.transaction do
      item = SubmissionGroupCase.lock.find(case_id)
      next false unless item.submission_group_id == group_id &&
                        item.state == "running" && item.attempt_token == attempt
      child = item.submission
      child.assign_attributes(result)
      child.finished_at = Time.now.utc
      child.save!
      item.update!(state: "complete", finished_at: child.finished_at)
      true
    end
  end

  def deliver_inline(child, executor)
    executor.send(:call_callback, child.reload)
  rescue StandardError => error
    Rails.logger.warn({event: "group_callback_failed", submission_id: child.id,
                       error: error.class.name}.to_json)
  end

  def measure(stage, group_id, case_id)
    started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    yield
  ensure
    if ENV["RUNNER_BENCHMARK_TIMINGS"] == "1"
      Rails.logger.warn({event: "runner_stage", group_id: group_id, case_id: case_id,
                         stage: stage,
                         seconds: Process.clock_gettime(Process::CLOCK_MONOTONIC) - started,
                         at: Time.now.utc.iso8601(6)}.to_json)
    end
  end
end
