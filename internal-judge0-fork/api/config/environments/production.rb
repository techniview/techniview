Rails.application.configure do
  config.enable_reloading = false
  config.eager_load = true
  config.consider_all_requests_local = false
  config.action_controller.perform_caching = false
  config.cache_store = :null_store
  config.public_file_server.enabled = false
  config.log_level = :warn
  config.logger = ActiveSupport::Logger.new($stdout)
  config.active_record.dump_schema_after_migration = false
end
