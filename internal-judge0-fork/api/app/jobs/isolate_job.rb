require "open3"
require "tmpdir"

class IsolateJob < ApplicationJob
  queue_as ENV.fetch("JUDGE0_VERSION")
  BOX_COUNT = 1000
  PYTHON = "/opt/python/bin/python3.14"

  def perform(submission_id)
    submission = Submission.find(submission_id)
    submission.update!(status: Status.process, started_at: Time.now.utc,
                       execution_host: ENV["HOSTNAME"])
    results = []
    submission.number_of_runs.times do
      result = execute(submission)
      results << result
      submission.assign_attributes(result)
      break unless submission.status == Status.ac
    end
    submission.time = results.sum { |result| result[:time].to_f } / results.size
    submission.memory = results.map { |result| result[:memory].to_i }.max
    submission.finished_at = Time.now.utc
    submission.save!
  rescue StandardError => error
    raise unless submission
    Rails.logger.error({event: "runner_execution_error", error: error.class.name}.to_json)
    submission.update!(status: Status.boxerr, message: "Sandbox execution failed.",
                       finished_at: Time.now.utc)
  ensure
    call_callback(submission) if submission
  end

  private

  def with_box
    BOX_COUNT.times do |id|
      File.open("/run/isolate/slots/#{id}", "w", 0600) do |lock|
        next unless lock.flock(File::LOCK_EX | File::LOCK_NB)
        initialized = false
        begin
          path, _error, status = Open3.capture3("isolate", "--cg", "-b", id.to_s, "--init")
          raise "Sandbox initialization failed" unless status.success?
          initialized = true
          path = path.strip
          raise "Unexpected sandbox path" unless path == "/var/local/lib/isolate/#{id}"
          return yield(id, path)
        ensure
          if initialized
            _output, _error, status = Open3.capture3("isolate", "--cg", "-b", id.to_s, "--cleanup")
            raise "Sandbox cleanup failed" unless status.success?
          end
        end
      end
    end
    raise "No sandbox slots available"
  end

  def execute(submission)
    with_box do |id, path|
      File.binwrite("#{path}/box/script.py", submission.source_code)
      Dir.mktmpdir("execution-") do |files|
        File.binwrite("#{files}/stdin", submission.stdin.to_s)
        arguments = [
          "isolate", "-s", "--cg", "-b", id.to_s, "-M", "#{files}/metadata",
          "-t", submission.cpu_time_limit.to_s, "-x", submission.cpu_extra_time.to_s,
          "-w", submission.wall_time_limit.to_s, "-k", submission.stack_limit.to_s,
          "-p#{submission.max_processes_and_or_threads}",
          "--cg-mem=#{submission.memory_limit}", "-f", submission.max_file_size.to_s,
          "--no-default-dirs", "--dir=box=./box:rw", "--dir=tmp:tmp",
          "--dir=lib=/usr/lib", "--dir=lib64=/usr/lib64:maybe",
          "--dir=usr/lib=/usr/lib", "--dir=opt/python=/opt/python",
          "-E", "HOME=/tmp", "-E", "LANG=C.UTF-8",
          "--run", "--", PYTHON, "-I", "-B", "script.py"
        ]
        # File redirection makes Isolate's output size limit effective; pipes do not.
        system(*arguments, in: "#{files}/stdin", out: "#{files}/stdout", err: "#{files}/stderr")
        exit_status = $?.exitstatus
        raise "Isolate failed" unless [0, 1].include?(exit_status)
        metadata = File.readlines("#{files}/metadata", chomp: true)
                       .to_h { |line| line.split(":", 2) }
        stdout = File.binread("#{files}/stdout")
        stderr = File.binread("#{files}/stderr")
        stdout, stderr = [stdout + stderr, ""] if submission.redirect_stderr_to_stdout
        {
          status: result_status(metadata, submission.expected_output, stdout),
          time: metadata.fetch("time"), wall_time: metadata.fetch("time-wall"),
          memory: Integer(metadata.fetch("cg-mem")),
          stdout: stdout.presence, stderr: stderr.presence,
          exit_code: metadata.fetch("exitcode", "0").to_i,
          exit_signal: metadata["exitsig"]&.to_i, message: metadata["message"]
        }
      end
    end
  end

  def result_status(metadata, expected, actual)
    case metadata["status"]
    when "TO" then Status.tle
    when "SG" then Status.find_runtime_error_by_status_code(metadata["exitsig"])
    when "RE" then Status.nzec
    when "XX" then Status.boxerr
    else
      expected.nil? || normalized(expected) == normalized(actual) ? Status.ac : Status.wa
    end
  end

  def normalized(value)
    value.lines.map(&:rstrip).join("\n").rstrip
  end

  def call_callback(submission)
    return if submission.callback_url.blank?
    payload = ActiveModelSerializers::SerializableResource.new(
      submission, serializer: SubmissionSerializer, base64_encoded: true,
      fields: SubmissionSerializer.default_fields
    ).to_json
    Config::CALLBACKS_MAX_TRIES.times do
      begin
        response = HTTParty.put(submission.callback_url, body: payload,
                               headers: {"Content-Type" => "application/json"},
                               timeout: Config::CALLBACKS_TIMEOUT,
                               follow_redirects: false)
        return if response.code.between?(200, 299)
        Rails.logger.warn({event: "runner_callback_rejected", status: response.code}.to_json)
      rescue StandardError => error
        Rails.logger.warn({event: "runner_callback_failed", error: error.class.name}.to_json)
      end
    end
  end
end
