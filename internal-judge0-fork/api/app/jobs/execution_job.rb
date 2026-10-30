class ExecutionJob < ApplicationJob
  queue_as ENV.fetch("JUDGE0_VERSION")

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
    submission.update!(status: Status.boxerr, message: execution_error_message(error),
                       finished_at: Time.now.utc)
  ensure
    call_callback(submission) if submission
  end

  private

  def execute(submission)
    GoJudgeExecutor.execute(submission)
  end

  def execution_error_message(error)
    error.is_a?(GoJudgeExecutor::OutcomeUnknown) ? "runner_outcome_unknown" : "Sandbox execution failed."
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
