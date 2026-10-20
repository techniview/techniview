require_relative "boot"
require "rails"
require "active_model/railtie"
require "active_job/railtie"
require "active_record/railtie"
require "action_controller/railtie"
Bundler.require(*Rails.groups)

module Judge0API
  class Application < Rails::Application
    config.load_defaults 8.1
    config.api_only = true
    config.active_job.queue_adapter = :resque
    config.active_job.enqueue_after_transaction_commit = :always
    config.hosts.clear
    config.filter_parameters += %i[source_code stdin expected_output stdout stderr
                                   compile_output callback_url password token]
  end
end
