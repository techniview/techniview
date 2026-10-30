class SubmissionGroup < ApplicationRecord
  has_many :group_cases, class_name: "SubmissionGroupCase", dependent: :restrict_with_exception

  def self.publish_due
    where.not(state: "complete").where("last_enqueued_at IS NULL OR last_enqueued_at < ?", 30.seconds.ago)
      .order(:id).limit(100).pluck(:id).each do |id|
      transaction do
        group = lock.find_by(id: id)
        next unless group && group.state != "complete" &&
                    (group.last_enqueued_at.nil? || group.last_enqueued_at < 30.seconds.ago)
        clock = {"boot_id" => File.read("/proc/sys/kernel/random/boot_id").strip,
                 "enqueued" => Process.clock_gettime(Process::CLOCK_MONOTONIC)}
        GroupJob.perform_later(group.id, clock)
        group.update!(last_enqueued_at: Time.now.utc)
      end
    end
  end
end
