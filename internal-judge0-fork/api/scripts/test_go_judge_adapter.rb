require "ostruct"
raise "Disposable tests only" unless ENV["RUNNER_ADAPTER_TESTS"] == "1"
submission = OpenStruct.new(expected_output: "42\n", redirect_stderr_to_stdout: false, max_file_size: 8, cpu_time_limit: 2)
base = {"status" => "Accepted", "files" => {"stdout" => "42\n", "stderr" => ""},
        "time" => 1_000_000, "runTime" => 2_000_000, "memory" => 1025, "exitStatus" => 0}
result = GoJudgeExecutor.result(submission, base)
raise "units wrong" unless result[:time] == 0.001 && result[:wall_time] == 0.002 && result[:memory] == 2
raise "accepted wrong" unless result[:status] == Status.ac
soft_limit = GoJudgeExecutor.result(submission, base.merge("time" => 2_100_000_000))
raise "extra time enlarged passing budget" unless soft_limit[:status] == Status.tle
overflow = GoJudgeExecutor.result(submission, base.merge("status" => "Output Limit Exceeded", "files" => {"stdout" => "x" * (8 * 1024 + 1)}))
raise "output budget exceeded" unless overflow[:stdout].bytesize == submission.max_file_size * 1024
raise "output verdict lost" unless overflow[:status] == Status.sigxfsz
raise "wrong answer trusted" unless GoJudgeExecutor.result(submission, base.merge("files" => {"stdout" => "41"}))[:status] == Status.wa
{
  "Time Limit Exceeded" => Status.tle, "Output Limit Exceeded" => Status.sigxfsz,
  "Memory Limit Exceeded" => Status.other, "Nonzero Exit Status" => Status.nzec,
  "Internal Error" => Status.boxerr, "File Error" => Status.boxerr,
  "unknown-status" => Status.boxerr
}.each do |name, expected|
  raise "status wrong: #{name}" unless GoJudgeExecutor.result(submission, base.merge("status" => name))[:status] == expected
end

submission = OpenStruct.new(source_code: "print(42)", stdin: "", max_file_size: 1024,
  cpu_time_limit: 2, cpu_extra_time: 0.5, wall_time_limit: 5, memory_limit: 128000,
  stack_limit: 64000, max_processes_and_or_threads: 1)
ENV["GO_JUDGE_URL"] = "http://go-judge:5050"
class << Net::HTTP
  attr_accessor :request_count
  alias_method :original_start, :start
  def start(*_args, **kwargs)
    raise "automatic retry enabled" unless kwargs[:max_retries] == 0
    self.request_count = (request_count || 0) + 1
    raise IOError, "response lost after execution"
  end
end
begin
  GoJudgeExecutor.execute(submission)
  raise "ambiguous execution accepted"
rescue GoJudgeExecutor::OutcomeUnknown
  raise "execution repeated" unless Net::HTTP.request_count == 1
ensure
  class << Net::HTTP
    alias_method :start, :original_start
  end
end
puts "go-judge adapter checks passed: units, verdicts, malformed status, ambiguous outcome without retry."
