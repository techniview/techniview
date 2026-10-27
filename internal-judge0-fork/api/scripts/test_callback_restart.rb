raise "Disposable test stack only" unless ENV["RUNNER_OUTBOX_TESTS"] == "1"
marker = "http://backend:8000/api/internal/judge0/callbacks/restart-test-only"
case ARGV.fetch(0)
when "setup"
  reference = Submission.where(status_id: Status.ac.id).first!
  Submission.transaction do
    specimen = reference.dup
    specimen.callback_url = marker
    specimen.save!
    CallbackDelivery.create!(submission_id: specimen.id, url: marker,
                             payload: "{}", next_attempt_at: Time.now.utc - 1)
  end
  puts "Pending callback committed before process exit."
when "recover"
  delivery = CallbackDelivery.find_by!(url: marker)
  before = Submission.find(delivery.submission_id).attributes
  def HTTParty.put(*_args, **_kwargs)
    Struct.new(:code).new(200)
  end
  raise "callback not recovered" unless CallbackDelivery.deliver_next
  raise "callback not delivered" unless delivery.reload.delivered_at
  raise "grading changed during delivery" unless Submission.find(delivery.submission_id).attributes == before
  raise "duplicate delivery" if CallbackDelivery.deliver_next
  id = delivery.submission_id
  delivery.destroy!
  Submission.find(id).destroy!
  puts "Callback recovered in a new process without changing grading."
else
  raise "Expected setup or recover"
end
