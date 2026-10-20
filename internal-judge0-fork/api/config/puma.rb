thread_count = Integer(ENV.fetch("RAILS_MAX_THREADS", "4"))
threads thread_count, thread_count
workers Integer(ENV.fetch("RAILS_SERVER_PROCESSES", "0"))
bind "tcp://#{ENV.fetch("BIND_HOST", "0.0.0.0")}:#{Integer(ENV.fetch("PORT", "2358"))}"
environment ENV.fetch("RAILS_ENV", "production")
