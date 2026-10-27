# Run with bundle exec ruby -r ./config/environment scripts/callbacks.rb.
stopping = false
Signal.trap("TERM") { stopping = true }
Signal.trap("INT") { stopping = true }
until stopping
  begin
    worked = CallbackDelivery.deliver_next
  rescue StandardError => error
    Rails.logger.error({event: "callback_delivery_worker_error", error: error.class.name}.to_json)
    worked = false
  end
  sleep 0.1 unless worked
end
