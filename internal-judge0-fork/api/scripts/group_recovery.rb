loop do
  begin
    SubmissionGroup.publish_due
  rescue StandardError => error
    Rails.logger.error({event: "group_recovery_failed", error: error.class.name}.to_json)
  end
  sleep 10
end
