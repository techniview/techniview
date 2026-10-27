class CallbackDelivery < ApplicationRecord
  MAX_ATTEMPTS = 8

  def self.deliver_next
    transaction do
      delivery = where(delivered_at: nil, exhausted_at: nil)
                 .where("next_attempt_at <= ?", Time.now.utc)
                 .order(:next_attempt_at, :id).lock("FOR UPDATE SKIP LOCKED").first
      return false unless delivery

      delivery.attempts += 1
      started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
      begin
        response = HTTParty.put(delivery.url, body: delivery.payload,
                                headers: {"Content-Type" => "application/json"},
                                timeout: Config::CALLBACKS_TIMEOUT, follow_redirects: false)
        delivery.last_status = response.code
        delivery.delivered_at = Time.now.utc if response.code.between?(200, 299)
      rescue StandardError => error
        Rails.logger.warn({event: "outbox_callback_failed", delivery_id: delivery.id,
                           error: error.class.name}.to_json)
      end
      unless delivery.delivered_at
        if delivery.attempts >= MAX_ATTEMPTS
          delivery.exhausted_at = Time.now.utc
        else
          delivery.next_attempt_at = Time.now.utc + [2 ** delivery.attempts, 60].min
        end
      end
      delivery.save!
      Rails.logger.warn({event: "outbox_callback_delivery", delivery_id: delivery.id,
                         submission_id: delivery.submission_id, attempt: delivery.attempts,
                         delivered: !delivery.delivered_at.nil?,
                         seconds: Process.clock_gettime(Process::CLOCK_MONOTONIC) - started,
                         at: Time.now.utc.iso8601(6)}.to_json)
      true
    end
  end
end
