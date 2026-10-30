require "net/http"
require "json"

# Expected outputs stay outside student-controlled execution.
module GoJudgeExecutor
  PYTHON = "/opt/python/bin/python3.14"

  class OutcomeUnknown < StandardError; end

  def self.execute(submission)
    uri = URI(ENV.fetch("GO_JUDGE_URL") + "/run")
    output_limit = submission.max_file_size * 1024
    command = {
      args: ["/usr/bin/prlimit", "--fsize=#{output_limit}:#{output_limit}", "--",
             PYTHON, "-I", "-B", "script.py"],
      env: ["HOME=/tmp", "LANG=C.UTF-8"],
      files: [{content: submission.stdin.to_s}, {name: "stdout", max: output_limit},
              {name: "stderr", max: output_limit}],
      copyIn: {"script.py" => {content: submission.source_code}},
      cpuLimit: submission.cpu_time_limit.positive? ? ((submission.cpu_time_limit + submission.cpu_extra_time) * 1_000_000_000).to_i : 0,
      clockLimit: (submission.wall_time_limit * 1_000_000_000).to_i,
      memoryLimit: submission.memory_limit * 1024,
      strictMemoryLimit: true,
      stackLimit: submission.stack_limit * 1024,
      procLimit: submission.max_processes_and_or_threads
    }
    request = Net::HTTP::Post.new(uri.request_uri, "Content-Type" => "application/json")
    request.body = JSON.generate(cmd: [command])
    response = Net::HTTP.start(uri.hostname, uri.port, open_timeout: 5,
                               read_timeout: submission.wall_time_limit.to_f + 5,
                               max_retries: 0) { |http| http.request(request) }
    raise OutcomeUnknown, "Execution service did not return a result; not retried" unless response.code == "200"
    reports = JSON.parse(response.body)
    raise OutcomeUnknown, "Invalid execution response; not retried" unless reports.is_a?(Array) && reports.size == 1
    raise OutcomeUnknown, "Invalid execution result; not retried" unless reports.first.is_a?(Hash)
    result(submission, reports.fetch(0))
  rescue IOError, SystemCallError, Timeout::Error, JSON::ParserError, KeyError, TypeError => error
    raise OutcomeUnknown, "#{error.class}: execution outcome unknown; not retried"
  end

  def self.result(submission, report)
    %w[time runTime memory].each do |key|
      value = report.fetch(key)
      raise TypeError, "Invalid execution resource value" unless value.is_a?(Numeric) && value >= 0
    end
    files = report.fetch("files", {})
    raise TypeError, "Invalid execution output" unless files.is_a?(Hash)
    stdout = files.fetch("stdout", "")
    stderr = files.fetch("stderr", "")
    raise TypeError, "Invalid output encoding" unless stdout.is_a?(String) && stderr.is_a?(String)
    # The collector may include an overflow byte when reporting output termination.
    output_limit = submission.max_file_size * 1024
    output_exceeded = stdout.bytesize > output_limit || stderr.bytesize > output_limit
    stdout = stdout.byteslice(0, output_limit)
    stderr = stderr.byteslice(0, output_limit)
    stdout, stderr = [stdout + stderr, ""] if submission.redirect_stderr_to_stdout
    status = case report.fetch("status")
             when "Accepted"
               if output_exceeded
                 Status.sigxfsz
               elsif submission.cpu_time_limit.positive? && report.fetch("time") > (submission.cpu_time_limit * 1_000_000_000).to_i
                 Status.tle
               else
                 expected = submission.expected_output
                 expected.nil? || normalized(expected) == normalized(stdout) ? Status.ac : Status.wa
               end
             when "Time Limit Exceeded" then Status.tle
             when "Memory Limit Exceeded" then Status.other
             when "Output Limit Exceeded" then Status.sigxfsz
             when "Nonzero Exit Status" then Status.nzec
             when "Signalled" then Status.find_runtime_error_by_status_code(report.fetch("exitStatus"))
             when "Dangerous Syscall" then Status.other
             else Status.boxerr
             end
    {
      status: status, stdout: stdout.empty? ? nil : stdout, stderr: stderr.empty? ? nil : stderr,
      time: report.fetch("time") / 1_000_000_000.0,
      wall_time: report.fetch("runTime") / 1_000_000_000.0,
      memory: (report.fetch("memory") / 1024.0).ceil,
      exit_code: report["status"] == "Signalled" ? nil : report["exitStatus"],
      exit_signal: report["status"] == "Signalled" ? report["exitStatus"] : nil,
      message: status == Status.boxerr ? "Execution infrastructure failed." : nil
    }
  end

  def self.normalized(value)
    value.lines.map(&:rstrip).join("\n").rstrip
  end
end
