raise "Disposable test stack only" unless ENV["RUNNER_OUTBOX_TESTS"] == "1"
raise "Outbox profile required" unless ENV["RUNNER_CALLBACK_OUTBOX"] == "1"

class CallbackTestJob < IsolateJob
  attr_reader :executions

  def execute(_submission)
    @executions = (@executions || 0) + 1
    {status: Status.ac, time: "0.001", memory: 4096, stdout: "42", stderr: nil}
  end
end

class << HTTParty
  attr_accessor :test_response
  alias_method :original_put, :put
  def put(*_arguments, **_keywords)
    raise IOError, "lost response" if test_response == :lost
    Struct.new(:code).new(test_response)
  end
end

CallbackDelivery.transaction do
  CallbackDelivery.delete_all
  reference = Submission.where(status_id: Status.ac.id).first!
  specimen = reference.dup
  specimen.callback_url = "http://backend:8000/api/internal/judge0/callbacks/test-only"
  specimen.save!
  job = CallbackTestJob.new
  job.perform(specimen.id)
  delivery = CallbackDelivery.find_by!(submission_id: specimen.id)
  raise "result not saved" unless specimen.reload.status_id == Status.ac.id
  raise "payload missing" unless JSON.parse(delivery.payload)["status"]["id"] == Status.ac.id

  HTTParty.test_response = :lost
  CallbackDelivery.deliver_next
  raise "lost response not recorded" unless delivery.reload.attempts == 1
  raise "retry not scheduled" unless delivery.next_attempt_at > Time.now.utc
  raise "retried too soon" if CallbackDelivery.deliver_next

  delivery.update!(next_attempt_at: Time.now.utc - 1)
  HTTParty.test_response = 503
  CallbackDelivery.deliver_next
  raise "rejection not recorded" unless delivery.reload.last_status == 503

  delivery.update!(next_attempt_at: Time.now.utc - 1)
  HTTParty.test_response = 200
  CallbackDelivery.deliver_next
  raise "not delivered" unless delivery.reload.delivered_at
  raise "delivered twice" if CallbackDelivery.deliver_next
  raise "student code reexecuted" unless job.executions == 1

  delivery.update!(delivered_at: nil, attempts: CallbackDelivery::MAX_ATTEMPTS - 1,
                   next_attempt_at: Time.now.utc - 1)
  HTTParty.test_response = 404
  CallbackDelivery.deliver_next
  raise "retries unbounded" unless delivery.reload.exhausted_at
  raise "exhausted retried" if CallbackDelivery.deliver_next

  previous = specimen.reload.stdout
  begin
    Submission.transaction(requires_new: true) do
      specimen.update!(stdout: "uncommitted result")
      CallbackDelivery.create!(submission_id: specimen.id, url: delivery.url,
                               payload: "{}", next_attempt_at: Time.now.utc)
    end
    raise "expected uniqueness rejection"
  rescue ActiveRecord::RecordNotUnique
    raise "result escaped transaction" unless specimen.reload.stdout == previous
  end
  raise ActiveRecord::Rollback
end
puts "Callback outbox checks passed: lost response, rejection, delay, duplicate, exhaustion, atomicity, no reexecution."
