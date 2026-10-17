Resque.redis = Redis.new(
  host: ENV.fetch("REDIS_HOST"),
  port: Integer(ENV.fetch("REDIS_PORT")),
  password: ENV.fetch("REDIS_PASSWORD")
)
